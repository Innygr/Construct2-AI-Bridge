"""Dependency-free client for the bridge's agent coordination API.

Follows docs/AGENT_PROTOCOL.md: claim a task, lock files before editing, publish
messages, mark the task in_review, release locks. The key safety property is
honesty about reachability: if the API cannot be reached the client raises
``CoordinationUnavailable`` rather than returning anything that looks like a
successful sync, so an agent never believes it holds a claim or lock it doesn't.

Loopback only. Agent names are labels, not authenticated identities.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import PurePosixPath
from typing import Any, Iterator

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class CoordinationUnavailable(Exception):
    """The coordination API could not be reached; nothing was synchronized."""


class CoordinationRequestError(Exception):
    """The API answered with an error (for example a 409 claim or lock conflict)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


def _safe_lock_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or not parsed.parts or any(part in ("", ".", "..") for part in parsed.parts):
        raise ValueError("Lock paths must be safe project-relative paths.")
    return parsed.as_posix()


class CoordinationClient:
    def __init__(self, agent: str, base_url: str = DEFAULT_BASE_URL, timeout: float = 5.0):
        if not agent or len(agent) > 80:
            raise ValueError("agent must be 1-80 characters (use 'claude', 'chatgpt' or 'local').")
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "http" or (parsed.hostname or "") not in LOOPBACK_HOSTS:
            raise ValueError("Coordination is loopback-only; use an http://127.0.0.1 or http://localhost URL.")
        self.agent = agent
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._tokens: dict[str, str] = {}  # path -> lock token held by this client

    # -- transport ----------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None,
                 query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}/api/coordination/{path.lstrip('/')}"
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(8_000_000)
        except urllib.error.HTTPError as exc:
            raise CoordinationRequestError(exc.code, self._detail(exc.read(8000))) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CoordinationUnavailable(
                f"Coordination API at {self.base_url} is unreachable ({exc}); not synchronized."
            ) from exc
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CoordinationRequestError(502, "Coordination API returned a non-JSON response.") from exc
        if not isinstance(parsed, dict):
            raise CoordinationRequestError(502, "Coordination API returned an unexpected response shape.")
        return parsed

    @staticmethod
    def _detail(raw: bytes) -> str:
        text = raw.decode("utf-8", errors="replace")
        try:
            detail = json.loads(text).get("detail", text)
        except (json.JSONDecodeError, AttributeError):
            return text[:500]
        return detail if isinstance(detail, str) else json.dumps(detail)[:500]

    # -- status -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return self._request("GET", "status")

    def available(self) -> bool:
        try:
            return bool(self.status().get("available"))
        except (CoordinationUnavailable, CoordinationRequestError):
            return False

    # -- tasks --------------------------------------------------------------

    def list_tasks(self, status: str | None = None) -> list[dict[str, Any]]:
        return self._request("GET", "tasks", query={"status": status})["tasks"]

    def create_task(self, title: str, description: str = "") -> dict[str, Any]:
        return self._request("POST", "tasks", {"title": title, "description": description,
                                               "created_by": self.agent})["task"]

    def claim_task(self, task_id: str, branch: str | None = None) -> dict[str, Any]:
        return self._request("POST", f"tasks/{urllib.parse.quote(task_id, safe='')}/claim",
                             {"agent": self.agent, "branch": branch})["task"]

    def update_task(self, task_id: str, status: str, branch: str | None = None) -> dict[str, Any]:
        return self._request("PATCH", f"tasks/{urllib.parse.quote(task_id, safe='')}",
                             {"agent": self.agent, "status": status, "branch": branch})["task"]

    def mark_in_review(self, task_id: str, branch: str | None = None) -> dict[str, Any]:
        return self.update_task(task_id, "in_review", branch)

    # -- messages -----------------------------------------------------------

    def post_message(self, body: str, task_id: str | None = None) -> dict[str, Any]:
        return self._request("POST", "messages", {"agent": self.agent, "body": body, "task_id": task_id})["message"]

    def messages(self, after_id: int = 0, task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", "messages", query={"after_id": after_id, "task_id": task_id,
                                                       "limit": limit})["messages"]

    # -- locks --------------------------------------------------------------

    def list_locks(self) -> list[dict[str, Any]]:
        return self._request("GET", "locks")["locks"]

    def acquire_lock(self, path: str, task_id: str | None = None, ttl_seconds: int = 900) -> dict[str, Any]:
        safe = _safe_lock_path(path)
        lock = self._request("POST", "locks", {"path": safe, "agent": self.agent,
                                               "task_id": task_id, "ttl_seconds": ttl_seconds})["lock"]
        self._tokens[safe] = lock["token"]
        return lock

    def release_lock(self, path: str, token: str | None = None) -> None:
        safe = _safe_lock_path(path)
        token = token or self._tokens.get(safe)
        if not token:
            raise ValueError(f"No lock token known for {safe}; pass the token returned by acquire_lock.")
        self._request("DELETE", "locks", {"path": safe, "agent": self.agent, "token": token})
        self._tokens.pop(safe, None)

    def release_all(self) -> list[tuple[str, str]]:
        """Release every lock this client holds; return (path, error) for any that failed."""
        failures: list[tuple[str, str]] = []
        for path in list(self._tokens):
            try:
                self.release_lock(path)
            except (CoordinationUnavailable, CoordinationRequestError) as exc:
                failures.append((path, str(exc)))
                self._tokens.pop(path, None)  # expired or unreachable: don't retry forever
        return failures

    @contextmanager
    def lock(self, paths: str | list[str], task_id: str | None = None, ttl_seconds: int = 900) -> Iterator[list[dict[str, Any]]]:
        """Hold locks on all ``paths`` for the block; all-or-nothing acquire, always release."""
        wanted = [paths] if isinstance(paths, str) else list(paths)
        acquired: list[dict[str, Any]] = []
        try:
            for path in wanted:
                acquired.append(self.acquire_lock(path, task_id, ttl_seconds))
            yield acquired
        finally:
            for lock in acquired:
                try:
                    self.release_lock(lock["path"], lock["token"])
                except (CoordinationUnavailable, CoordinationRequestError):
                    pass  # best effort: locks also expire after their TTL
