"""Read-only MCP server (stdio) for Construct 2 AI Bridge.

Speaks newline-delimited JSON-RPC 2.0 so MCP-capable AI clients can inspect a
Construct 2 project without any extra dependencies. Every tool is read-only:
this server never writes to a project file. Edits stay with the reviewed
write/patch workflow in the local bridge UI.

Run with ``construct2-ai-bridge-mcp`` and register it as a stdio server in your
MCP client. Stdout carries protocol messages only; diagnostics go to stderr.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, TextIO

from . import __version__
from .explain import explain_outlines
from .lint import lint_summary
from .project_reader import ProjectDocument, ProjectReadError, inspect_project, load_project

SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_XML_RESULT_CHARS = 400_000
MAX_LIST_LIMIT = 500

_document: ProjectDocument | None = None
_summary: dict[str, Any] | None = None


class ToolError(Exception):
    """A tool failed in a way the model should see and can act on."""


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _require_project() -> tuple[ProjectDocument, dict[str, Any]]:
    if _document is None or _summary is None:
        raise ToolError("No project is open. Call open_project with an absolute path first.")
    return _document, _summary


def _all_events(summary: dict[str, Any], document: str | None) -> list[dict[str, Any]]:
    return [
        event
        for outline in summary.get("event_outlines", [])
        if document is None or outline.get("document") == document
        for event in outline.get("events", [])
    ]


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def _opt_str(args: dict[str, Any], key: str) -> str | None:
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ToolError(f"'{key}' must be a string.")
    return value


def _int(args: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(f"'{key}' must be an integer.")
    return max(low, min(high, value))


def tool_open_project(args: dict[str, Any]) -> str:
    global _document, _summary
    path = args.get("path")
    if not isinstance(path, str) or not path:
        raise ToolError("'path' is required and must be an absolute path to a .capx, .caproj, .c2proj or .xml file.")
    try:
        document = load_project(path)
        summary = inspect_project(document)
    except (ProjectReadError, OSError) as exc:
        raise ToolError(f"Could not open project: {exc}") from exc
    _document, _summary = document, summary
    return _text({
        "opened": True,
        "path": summary["path"],
        "kind": summary["kind"],
        "xml_documents": summary["xml_documents"],
        "counts": summary["counts"],
        "layouts": summary["layouts"],
        "event_sheets": summary["event_sheets"],
        "diagnostics": summary["diagnostics"],
    })


def tool_project_summary(args: dict[str, Any]) -> str:
    _, summary = _require_project()
    slim = {key: value for key, value in summary.items() if key != "event_outlines"}
    slim["outline_documents"] = [
        {"document": o["document"], "event_count": o["event_count"], "truncated": o["truncated"]}
        for o in summary.get("event_outlines", [])
    ]
    return _text(slim)


def tool_list_events(args: dict[str, Any]) -> str:
    _, summary = _require_project()
    document = _opt_str(args, "document")
    limit = _int(args, "limit", 50, 1, MAX_LIST_LIMIT)
    offset = _int(args, "offset", 0, 0, 10**9)
    events = _all_events(summary, document)
    page = events[offset : offset + limit]
    rows = [
        {
            "event_id": e["event_id"], "depth": e["depth"], "kind": e["kind"], "label": e["label"],
            "conditions": e["condition_count"], "actions": e["action_count"],
            "sub_events": e["child_event_count"], **({"disabled": True} if e.get("disabled") else {}),
        }
        for e in page
    ]
    return _text({"total": len(events), "offset": offset, "returned": len(rows), "events": rows})


def tool_explain_events(args: dict[str, Any]) -> str:
    _, summary = _require_project()
    ids = args.get("event_ids")
    if ids is not None and not (isinstance(ids, list) and all(isinstance(i, str) for i in ids)):
        raise ToolError("'event_ids' must be an array of strings.")
    known = {e["event_id"] for e in _all_events(summary, None)}
    unknown = sorted(set(ids or []) - known)
    if unknown:
        raise ToolError(f"Unknown event_id value(s): {', '.join(unknown)}")
    result = explain_outlines(
        summary.get("event_outlines", []),
        document=_opt_str(args, "document"),
        event_ids=set(ids) if ids else None,
        max_chars=_int(args, "max_chars", 12000, 1000, 100_000),
    )
    suffix = "\n\n(truncated: narrow with event_ids or document)" if result["truncated"] else ""
    return result["text"] + suffix if result["text"] else "No matching events."


def tool_lint_project(args: dict[str, Any]) -> str:
    _, summary = _require_project()
    return _text(lint_summary(summary))


def tool_get_xml(args: dict[str, Any]) -> str:
    document, _ = _require_project()
    name = args.get("document")
    if not isinstance(name, str) or not name:
        raise ToolError("'document' is required; use project_summary to see xml_documents.")
    available = dict(document.xml_documents)
    if name not in available:
        raise ToolError(f"Unknown XML document: {name}")
    xml = _decode(available[name])
    if len(xml) > MAX_XML_RESULT_CHARS:
        return xml[:MAX_XML_RESULT_CHARS] + f"\n<!-- truncated at {MAX_XML_RESULT_CHARS} of {len(xml)} characters -->"
    return xml


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


TOOLS: dict[str, tuple[str, dict[str, Any], Callable[[dict[str, Any]], str]]] = {
    "open_project": (
        "Open a Construct 2 project (.capx, .caproj, .c2proj or .xml) for read-only inspection. Must be called first.",
        _schema({"path": {"type": "string", "description": "Absolute path to the project file."}}, ["path"]),
        tool_open_project,
    ),
    "project_summary": (
        "Layouts, event sheets, objects, families, global variables, counts and diagnostics for the open project.",
        _schema({}),
        tool_project_summary,
    ),
    "list_events": (
        "Paged list of events (id, label, counts) so you can pick event_ids to explain.",
        _schema({
            "document": {"type": "string", "description": "Limit to one XML document."},
            "limit": {"type": "integer", "description": "Page size, 1-500 (default 50)."},
            "offset": {"type": "integer", "description": "Start index (default 0)."},
        }),
        tool_list_events,
    ),
    "explain_events": (
        "Readable IF/THEN rendering of events. Best-effort and derived only from the project XML.",
        _schema({
            "document": {"type": "string"},
            "event_ids": {"type": "array", "items": {"type": "string"}},
            "max_chars": {"type": "integer", "description": "Output budget, 1000-100000 (default 12000)."},
        }),
        tool_explain_events,
    ),
    "lint_project": (
        "Heuristic hints: empty events, events with no actions, disabled events, deep nesting, unused globals.",
        _schema({}),
        tool_lint_project,
    ),
    "get_xml": (
        "Full XML text of one document in the open project (capped at 400000 characters).",
        _schema({"document": {"type": "string", "description": "Name from project_summary.xml_documents."}}, ["document"]),
        tool_get_xml,
    ),
}


def _tool_listing() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": desc, "inputSchema": schema, "annotations": {"readOnlyHint": True}}
        for name, (desc, schema, _) in TOOLS.items()
    ]


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle_message(message: Any) -> dict[str, Any] | None:
    """Handle one decoded JSON-RPC message; return a response, or None for notifications."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
    method = message["method"]
    is_notification = "id" not in message
    msg_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return None if is_notification else _error(msg_id, -32602, "params must be an object")

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "construct2-ai-bridge", "version": __version__},
            "instructions": "Read-only access to a Construct 2 project. Call open_project first. "
                            "Output is best-effort; suggest changes, do not claim files were modified.",
        }}
    if is_notification:
        return None  # notifications/initialized, cancelled, etc.
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": _tool_listing()}}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOLS:
            return _error(msg_id, -32602, f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            return _error(msg_id, -32602, "arguments must be an object")
        try:
            text, is_error = TOOLS[name][2](arguments), False
        except ToolError as exc:
            text, is_error = str(exc), True
        except Exception as exc:  # keep the server alive; surface a safe message
            print(f"tool {name} crashed: {exc!r}", file=sys.stderr)
            text, is_error = f"Internal error while running {name}.", True
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": text}], "isError": is_error}}
    return _error(msg_id, -32601, f"Method not found: {method}")


def serve(stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response: dict[str, Any] | None = _error(None, -32700, "Parse error")
        else:
            response = handle_message(message)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            stdout.flush()


def main() -> None:
    serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
