import io
import json
import subprocess
import sys
from pathlib import Path

from construct2_ai_bridge import mcp_server
from construct2_ai_bridge.mcp_server import handle_message, serve

EVENTS = (
    '<c2project><globalVariables><globalvar name="Score" /></globalVariables>'
    '<events><event name="On start"><condition id="OnStart" />'
    '<action name="Set"><param name="v" value="10" /></action></event>'
    '<event name="Empty" /></events></c2project>'
)


def setup_function() -> None:
    mcp_server._document = None
    mcp_server._summary = None


def call(name: str, arguments: dict | None = None, msg_id: int = 1) -> dict:
    response = handle_message({"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
                               "params": {"name": name, "arguments": arguments or {}}})
    assert response is not None
    return response


def result_text(response: dict) -> str:
    return response["result"]["content"][0]["text"]


def open_sample(tmp_path: Path) -> Path:
    project = tmp_path / "game.caproj"
    project.write_text(EVENTS, encoding="utf-8")
    response = call("open_project", {"path": str(project)})
    assert response["result"]["isError"] is False
    return project


def test_initialize_negotiates_version_and_advertises_tools() -> None:
    response = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2024-11-05"}})
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in response["result"]["capabilities"]
    fallback = handle_message({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                               "params": {"protocolVersion": "1999-01-01"}})
    assert fallback["result"]["protocolVersion"] == "2025-06-18"


def test_notifications_get_no_response_and_unknown_methods_error() -> None:
    assert handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    response = handle_message({"jsonrpc": "2.0", "id": 5, "method": "nope"})
    assert response["error"]["code"] == -32601
    assert handle_message({"id": 1})["error"]["code"] == -32600


def test_tools_list_is_all_read_only() -> None:
    tools = handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {"open_project", "project_summary", "list_events", "explain_events", "lint_project", "get_xml"} <= names
    assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
    assert not any("write" in name or "patch" in name for name in names)


def test_tools_require_open_project() -> None:
    response = call("project_summary")
    assert response["result"]["isError"] is True
    assert "open_project" in result_text(response)


def test_open_project_rejects_bad_path_as_tool_error(tmp_path: Path) -> None:
    response = call("open_project", {"path": str(tmp_path / "missing.caproj")})
    assert response["result"]["isError"] is True
    assert "Could not open project" in result_text(response)


def test_list_and_explain_events(tmp_path: Path) -> None:
    open_sample(tmp_path)
    listing = json.loads(result_text(call("list_events")))
    assert listing["total"] == 2
    assert listing["events"][0]["event_id"] == "game.caproj::event:0001"
    page = json.loads(result_text(call("list_events", {"limit": 1, "offset": 1})))
    assert page["returned"] == 1 and page["events"][0]["label"] == "Empty"
    explained = result_text(call("explain_events", {"event_ids": ["game.caproj::event:0001"]}))
    assert "THEN Set(v=10)" in explained and "Empty" not in explained
    bad = call("explain_events", {"event_ids": ["game.caproj::event:9999"]})
    assert bad["result"]["isError"] is True


def test_lint_and_get_xml(tmp_path: Path) -> None:
    open_sample(tmp_path)
    lint = json.loads(result_text(call("lint_project")))
    assert any(f["code"] == "empty-event" for f in lint["findings"])
    assert result_text(call("get_xml", {"document": "game.caproj"})) == EVENTS
    assert call("get_xml", {"document": "other.xml"})["result"]["isError"] is True


def test_argument_validation(tmp_path: Path) -> None:
    open_sample(tmp_path)
    assert call("list_events", {"limit": "ten"})["result"]["isError"] is True
    assert call("nope")["error"]["code"] == -32602


def test_serve_handles_parse_errors_and_blank_lines() -> None:
    stdin = io.StringIO('\nnot json\n{"jsonrpc":"2.0","id":1,"method":"ping"}\n')
    stdout = io.StringIO()
    serve(stdin, stdout)
    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == -32700
    assert lines[1] == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_runs_as_stdio_subprocess(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    project.write_text(EVENTS, encoding="utf-8")
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "open_project", "arguments": {"path": str(project)}}},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "lint_project", "arguments": {}}},
    ]
    src = str(Path(mcp_server.__file__).resolve().parents[1])
    proc = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {src!r}); from construct2_ai_bridge.mcp_server import main; main()"],
        input="\n".join(json.dumps(m) for m in messages) + "\n",
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    replies = [json.loads(line) for line in proc.stdout.splitlines()]
    assert [r["id"] for r in replies] == [1, 2, 3]  # notification produced no reply
    assert replies[2]["result"]["isError"] is False
