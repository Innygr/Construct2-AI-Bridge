"""Tests for the MCP analysis tools without needing the MCP SDK or a running bridge.

``FakeMcp`` stands in for FastMCP: the module only uses its ``tool()`` decorator.
``fake_bridge`` serves /api/events and /api/objects from a real inspected project,
so the explainer and linter run against genuine project_reader output.
"""
import inspect
from pathlib import Path

import pytest

from construct2_ai_bridge.mcp_analysis_tools import build_tools, register
from construct2_ai_bridge.project_reader import inspect_project, load_project

XML = (
    '<c2project><globalVariables><globalvar name="Score" /><globalvar name="Lives" /></globalVariables>'
    '<events><event name="On start"><condition id="Compare"><param name="left" value="Score" /></condition>'
    '<action name="Set"><param name="v" value="10" /></action></event>'
    '<event name="Empty" /></events></c2project>'
)


class FakeMcp:
    def __init__(self) -> None:
        self.registered: dict[str, object] = {}

    def tool(self):
        def decorator(function):
            self.registered[function.__name__] = function
            return function
        return decorator


@pytest.fixture()
def fake_bridge(tmp_path: Path):
    project = tmp_path / "game.caproj"
    project.write_text(XML, encoding="utf-8")
    summary = inspect_project(load_project(project))
    calls: list[str] = []

    def request(path: str, **kwargs) -> dict:
        calls.append(path)
        if path == "/api/events":
            return {"event_outlines": summary["event_outlines"], "note": "best-effort"}
        if path == "/api/objects":
            return {"global_variables": summary["global_variables"]}
        raise AssertionError(f"unexpected bridge call: {path}")

    request.calls = calls  # type: ignore[attr-defined]
    return request


def test_register_exposes_only_the_two_read_only_tools(fake_bridge) -> None:
    mcp = FakeMcp()
    assert register(mcp, fake_bridge) == ["explain_events", "lint_project"]
    assert set(mcp.registered) == {"explain_events", "lint_project"}
    for function in mcp.registered.values():
        assert function.__doc__ and not inspect.iscoroutinefunction(function)
    assert fake_bridge.calls == []  # registering must not call the bridge


def test_explain_events_renders_and_filters(fake_bridge) -> None:
    explain = build_tools(fake_bridge)["explain_events"]
    full = explain()
    assert "IF   Compare(left=Score)" in full["text"] and "THEN Set(v=10)" in full["text"]
    assert full["note"] == "best-effort" and full["truncated"] is False and full["hint"] is None
    one = explain(event_ids=["game.caproj::event:0002"])
    assert one["included_event_count"] == 1 and "Empty" in one["text"] and "On start" not in one["text"]
    assert explain(document="other.xml")["included_event_count"] == 0


def test_explain_events_truncation_hint(fake_bridge) -> None:
    result = build_tools(fake_bridge)["explain_events"](max_chars=1000)
    assert result["truncated"] is False  # tiny project fits
    # Force truncation with a bigger project served by a stub bridge.
    events = [{"event_id": f"e::event:{i:04d}", "depth": 0, "kind": "event", "label": "x" * 80,
               "condition_count": 0, "action_count": 0, "child_event_count": 0} for i in range(60)]
    big = lambda path, **kw: {"event_outlines": [{"document": "e", "events": events}]}  # noqa: E731
    cut = build_tools(big)["explain_events"](max_chars=1000)
    assert cut["truncated"] is True and cut["hint"] and 0 < cut["included_event_count"] < 60


def test_explain_events_validates_input_before_calling_bridge(fake_bridge) -> None:
    explain = build_tools(fake_bridge)["explain_events"]
    for bad in ({"max_chars": 999}, {"max_chars": 40001}, {"event_ids": []}, {"event_ids": ["x"] * 101}):
        with pytest.raises(ValueError):
            explain(**bad)
    assert fake_bridge.calls == []
    with pytest.raises(ValueError, match="Unknown event_id value.*nope"):
        explain(event_ids=["nope"])


def test_lint_project_combines_events_and_objects(fake_bridge) -> None:
    result = build_tools(fake_bridge)["lint_project"]()
    codes = {(f["code"], f["event_id"]) for f in result["findings"]}
    assert ("empty-event", "game.caproj::event:0002") in codes
    messages = [f["message"] for f in result["findings"] if f["code"] == "unused-global-variable"]
    assert messages == ["Global variable 'Lives' is not mentioned in any event outline."]  # Score is used
    assert sorted(fake_bridge.calls) == ["/api/events", "/api/objects"]


def test_bridge_errors_propagate_unchanged() -> None:
    class Boom(RuntimeError):
        pass

    def request(path: str, **kwargs) -> dict:
        raise Boom("bridge down")

    for name in ("explain_events", "lint_project"):
        with pytest.raises(Boom, match="bridge down"):
            build_tools(request)[name]()
