"""Tests for CoordinationClient against a loopback stub backed by the real CoordinationStore.

The stub mirrors the route and payload shapes in server.py. It is NOT the real
FastAPI app (FastAPI isn't required to run these tests), so a separate check
against the live bridge is still needed to confirm the routes match.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from construct2_ai_bridge.coordination import CoordinationError, CoordinationStore
from construct2_ai_bridge.coordination_client import (
    CoordinationClient,
    CoordinationRequestError,
    CoordinationUnavailable,
)


def _make_handler(store: CoordinationStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # keep test output quiet
            pass

        def _send(self, status: int, payload, raw: bytes | None = None) -> None:
            body = raw if raw is not None else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def _route(self, method: str) -> None:
            parts = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}
            segs = [s for s in parts.path.split("/") if s]
            try:
                if segs[:2] != ["api", "coordination"]:
                    return self._send(404, {"detail": "Not Found"})
                tail = segs[2:]
                if tail == ["garbage"]:
                    return self._send(200, None, raw=b"<html>not json</html>")
                if method == "GET" and tail == ["status"]:
                    return self._send(200, {"available": True, "storage": "sqlite"})
                if method == "GET" and tail == ["tasks"]:
                    return self._send(200, {"tasks": store.list_tasks(query.get("status"))})
                if method == "POST" and tail == ["tasks"]:
                    b = self._body()
                    return self._send(200, {"task": store.create_task(b["title"], b.get("description", ""), b["created_by"])})
                if method == "POST" and len(tail) == 3 and tail[0] == "tasks" and tail[2] == "claim":
                    b = self._body()
                    return self._send(200, {"task": store.claim_task(tail[1], b["agent"], b.get("branch"))})
                if method == "PATCH" and len(tail) == 2 and tail[0] == "tasks":
                    b = self._body()
                    return self._send(200, {"task": store.update_task(tail[1], b["agent"], b["status"], b.get("branch"))})
                if method == "GET" and tail == ["messages"]:
                    return self._send(200, {"messages": store.list_messages(
                        query.get("task_id"), int(query.get("after_id", 0)), int(query.get("limit", 100)))})
                if method == "POST" and tail == ["messages"]:
                    b = self._body()
                    return self._send(200, {"message": store.post_message(b["agent"], b["body"], b.get("task_id"))})
                if method == "GET" and tail == ["locks"]:
                    return self._send(200, {"locks": store.list_locks()})
                if method == "POST" and tail == ["locks"]:
                    b = self._body()
                    return self._send(200, {"lock": store.acquire_lock(b["path"], b["agent"], b.get("task_id"), b["ttl_seconds"])})
                if method == "DELETE" and tail == ["locks"]:
                    b = self._body()
                    store.release_lock(b["path"], b["agent"], b["token"])
                    return self._send(200, {"released": True})
                return self._send(404, {"detail": "Not Found"})
            except CoordinationError as exc:
                return self._send(exc.status_code, {"detail": str(exc)})

        def do_GET(self) -> None: self._route("GET")
        def do_POST(self) -> None: self._route("POST")
        def do_PATCH(self) -> None: self._route("PATCH")
        def do_DELETE(self) -> None: self._route("DELETE")

    return Handler


@pytest.fixture()
def bridge(tmp_path: Path):
    store = CoordinationStore(tmp_path / "coord.sqlite3")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", store
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_full_agent_workflow(bridge) -> None:
    url, store = bridge
    chatgpt = CoordinationClient("chatgpt", url)
    claude = CoordinationClient("claude", url)
    assert claude.available() and claude.status()["storage"] == "sqlite"

    task = chatgpt.create_task("Parser", "Parse params")
    assert [t["id"] for t in claude.list_tasks("open")] == [task["id"]]
    claimed = claude.claim_task(task["id"], "claude/parser")
    assert claimed["owner"] == "claude" and claimed["branch"] == "claude/parser"

    with claude.lock(["src/a.py", "src/b.py"], task["id"]) as locks:
        assert {lock["path"] for lock in locks} == {"src/a.py", "src/b.py"}
        assert {lock["path"] for lock in store.list_locks()} == {"src/a.py", "src/b.py"}
        first = claude.post_message("working", task["id"])
    assert store.list_locks() == []  # released on exit

    claude.post_message("ready for review", task["id"])
    later = chatgpt.messages(after_id=first["id"], task_id=task["id"])
    assert [m["body"] for m in later] == ["ready for review"]
    assert claude.mark_in_review(task["id"])["status"] == "in_review"


def test_conflicts_surface_as_request_errors(bridge) -> None:
    url, _ = bridge
    claude, chatgpt = CoordinationClient("claude", url), CoordinationClient("chatgpt", url)
    task = claude.create_task("T")
    claude.claim_task(task["id"])
    with pytest.raises(CoordinationRequestError) as claim:
        chatgpt.claim_task(task["id"])
    assert claim.value.status_code == 409 and "claude" in claim.value.detail
    claude.acquire_lock("src/a.py")
    with pytest.raises(CoordinationRequestError) as lock:
        chatgpt.acquire_lock("src/a.py")
    assert lock.value.status_code == 409
    with pytest.raises(CoordinationRequestError) as missing:
        claude.claim_task("C2-NOPE0000")
    assert missing.value.status_code == 404


def test_lock_context_is_all_or_nothing_and_releases_on_error(bridge) -> None:
    url, store = bridge
    claude, chatgpt = CoordinationClient("claude", url), CoordinationClient("chatgpt", url)
    chatgpt.acquire_lock("src/b.py")
    with pytest.raises(CoordinationRequestError):
        with claude.lock(["src/a.py", "src/b.py"]):
            pytest.fail("block must not run when a lock is held by someone else")
    assert [(lock["path"], lock["agent"]) for lock in store.list_locks()] == [("src/b.py", "chatgpt")]

    with pytest.raises(RuntimeError):
        with claude.lock("src/c.py"):
            raise RuntimeError("boom")
    assert [lock["path"] for lock in store.list_locks()] == ["src/b.py"]  # c.py released despite the error


def test_release_helpers(bridge) -> None:
    url, store = bridge
    claude = CoordinationClient("claude", url)
    claude.acquire_lock("src/a.py")
    claude.acquire_lock("docs\\x.md")  # backslashes normalised like the server does
    assert {lock["path"] for lock in store.list_locks()} == {"src/a.py", "docs/x.md"}
    assert claude.release_all() == []
    assert store.list_locks() == []
    with pytest.raises(ValueError, match="No lock token"):
        claude.release_lock("src/never-locked.py")


def test_unreachable_api_raises_instead_of_pretending_to_sync() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]  # closed again on exit: nothing is listening
    client = CoordinationClient("claude", f"http://127.0.0.1:{port}", timeout=1.0)
    assert client.available() is False
    for call in (client.status, client.list_tasks, lambda: client.claim_task("C2-X"),
                 lambda: client.acquire_lock("src/a.py"), lambda: client.post_message("hi")):
        with pytest.raises(CoordinationUnavailable, match="not synchronized"):
            call()
    with pytest.raises(CoordinationUnavailable):
        with client.lock("src/a.py"):
            pytest.fail("block must not run without a real lock")


def test_non_json_response_is_an_error_not_data(bridge) -> None:
    url, _ = bridge
    with pytest.raises(CoordinationRequestError) as exc:
        CoordinationClient("claude", url)._request("GET", "garbage")
    assert exc.value.status_code == 502


@pytest.mark.parametrize("bad_url", ["http://192.168.1.5:8765", "https://127.0.0.1:8765", "http://example.com"])
def test_rejects_non_loopback_urls(bad_url: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        CoordinationClient("claude", bad_url)


def test_input_validation() -> None:
    with pytest.raises(ValueError):
        CoordinationClient("")
    client = CoordinationClient("claude")
    for bad in ("/etc/passwd", "../x.py", "a/../b.py", ""):
        with pytest.raises(ValueError, match="project-relative"):
            client.acquire_lock(bad)
