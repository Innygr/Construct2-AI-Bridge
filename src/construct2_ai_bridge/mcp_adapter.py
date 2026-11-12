"""MCP adapter for the local Construct 2 AI Bridge API.

Run with `construct2-ai-bridge-mcp` for stdio clients, or
`construct2-ai-bridge-mcp --transport http` for an authenticated
Streamable HTTP endpoint suitable for a user-managed HTTPS tunnel.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

API_BASE = os.environ.get("C2AB_API_URL", "http://127.0.0.1:8765").rstrip("/")
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 8766
mcp = FastMCP("Construct 2 AI Bridge")


class BridgeApiError(RuntimeError):
    """Raised when the local bridge API cannot complete a request."""


def _request(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
             query: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    url = API_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read(40_000_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(8000).decode("utf-8", errors="replace")
        raise BridgeApiError(f"Bridge API returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise BridgeApiError(
            f"Cannot reach Construct 2 AI Bridge at {API_BASE}. "
            "Start the local bridge first. Details: " + str(exc)
        ) from exc
    if not isinstance(result, dict):
        raise BridgeApiError("Bridge API returned an unexpected response.")
    return result


@mcp.tool()
def bridge_status() -> dict[str, Any]:
    """Check whether the local Construct 2 AI Bridge API is running."""
    return _request("/api/status")


@mcp.tool()
def get_project_state() -> dict[str, Any]:
    """Get the currently opened project, available XML documents, and edit version hash."""
    return _request("/api/project/state")


@mcp.tool()
def get_project_summary() -> dict[str, Any]:
    """Inspect layouts, event sheets, objects, variables, counts, and parser diagnostics."""
    return _request("/api/project/summary")


@mcp.tool()
def get_objects() -> dict[str, Any]:
    """List Construct 2 object types, families, and global variables."""
    return _request("/api/objects")


@mcp.tool()
def get_event_sheets() -> dict[str, Any]:
    """List event sheets and their best-effort event outlines."""
    return _request("/api/events")


@mcp.tool()
def get_event_details(event_ids: list[str]) -> dict[str, Any]:
    """Retrieve selected event outlines by their event_id values."""
    if not event_ids or len(event_ids) > 100:
        raise ValueError("Supply between 1 and 100 event_ids.")
    data = _request("/api/events")
    events = [
        event
        for outline in data.get("event_outlines", [])
        for event in outline.get("events", [])
        if event.get("event_id") in set(event_ids)
    ]
    found = {event.get("event_id") for event in events}
    missing = sorted(set(event_ids) - found)
    if missing:
        raise ValueError("Unknown event_id value(s): " + ", ".join(missing))
    return {"events": events, "count": len(events), "note": data.get("note")}


@mcp.tool()
def get_ai_context(event_ids: list[str] | None = None, max_chars: int = 12000) -> dict[str, Any]:
    """Get bounded, evidence-grounded debugging context for the whole project or selected events."""
    if not 1000 <= max_chars <= 40000:
        raise ValueError("max_chars must be between 1000 and 40000.")
    query = [("max_chars", str(max_chars))]
    for event_id in event_ids or []:
        query.append(("event_ids", event_id))
    return _request("/api/ai-context", query=query)


@mcp.tool()
def get_project_xml(documents: list[str]) -> dict[str, Any]:
    """Read the complete XML for explicitly selected project documents; open the project in the bridge UI first."""
    if not documents or len(documents) > 10:
        raise ValueError("Select between 1 and 10 XML document names.")
    query = [("documents", name) for name in documents]
    return _request("/api/project/xml", query=query)


@mcp.tool()
def get_xml_tree(document: str) -> dict[str, Any]:
    """Inspect a bounded XML node tree with child-index paths for one project document."""
    return _request("/api/project/tree", query=[("document", document)])


@mcp.tool()
def propose_xml_patch(document: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Prepare a non-mutating structural XML edit proposal. It never writes project files."""
    if not operations or len(operations) > 100:
        raise ValueError("Supply between 1 and 100 XML operations.")
    allowed = {"set_attribute", "remove_attribute", "set_text", "append_xml", "delete_node"}
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict) or operation.get("op") not in allowed:
            raise ValueError(f"Operation {index} has an unsupported op.")
        path = operation.get("path", [])
        if not isinstance(path, list) or len(path) > 128 or any(
            not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in path
        ):
            raise ValueError(f"Operation {index} has an invalid child-index path.")
        if operation["op"] == "delete_node" and not path:
            raise ValueError("Deleting the document root is not allowed.")
    state = _request("/api/project/state")
    tree = _request("/api/project/tree", query=[("document", document)])
    return {
        "proposal_only": True,
        "document": document,
        "expected_project_sha256": state["project_sha256"],
        "operations": operations,
        "current_xml_tree": tree["tree"],
        "approval_required": True,
        "instructions": "Review the target paths and operations. No project file has been changed. "
                        "To apply, obtain explicit user approval and call apply_approved_patch "
                        "with this exact project hash and the approved operations.",
    }


@mcp.tool()
def apply_approved_patch(
    document: str,
    expected_project_sha256: str,
    operations: list[dict[str, Any]],
    user_approved: bool,
) -> dict[str, Any]:
    """Apply an explicitly user-approved XML patch; creates a numbered backup and rejects stale project hashes."""
    if user_approved is not True:
        raise PermissionError("No project changes were made: user_approved must be true after explicit user approval.")
    if not operations or len(operations) > 100:
        raise ValueError("Supply between 1 and 100 XML operations.")
    return _request(
        "/api/project/patch",
        method="POST",
        payload={
            "document": document,
            "expected_project_sha256": expected_project_sha256,
            "operations": operations,
        },
    )


class BearerTokenMiddleware:
    """Require a constant-time-checked bearer token for every tunneled MCP HTTP request."""

    def __init__(self, app: Any, token: str):
        self.app = app
        self.expected = ("Bearer " + token).encode("utf-8")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        import hmac
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"authorization", b"")
        if not hmac.compare_digest(supplied, self.expected):
            body = b'{"error":"unauthorized"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def _token_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "construct2-ai-bridge" / "mcp-token"


def _load_or_create_token() -> str:
    configured = os.environ.get("C2AB_MCP_TOKEN")
    if configured:
        if len(configured) < 32:
            raise RuntimeError("C2AB_MCP_TOKEN must contain at least 32 characters.")
        return configured
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 32:
            return token
    token = secrets.token_urlsafe(48)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    print(f"Created MCP bearer token at: {path}", file=sys.stderr)
    print("Keep this token private. It is required by the HTTPS tunnel client.", file=sys.stderr)
    return token


def main() -> None:
    parser = argparse.ArgumentParser(description="Construct 2 AI Bridge MCP server")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio")
    parser.add_argument("--host", default=HTTP_HOST)
    parser.add_argument("--port", type=int, default=HTTP_PORT)
    args = parser.parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("The MCP HTTP server must bind to loopback; expose it only through an authenticated HTTPS tunnel.")
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    try:
        import uvicorn
        token = _load_or_create_token()
        app = BearerTokenMiddleware(mcp.streamable_http_app(), token)
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    except Exception as exc:
        print(f"Could not start MCP HTTP server: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
