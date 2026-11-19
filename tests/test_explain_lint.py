from pathlib import Path

from construct2_ai_bridge.explain import explain_outlines
from construct2_ai_bridge.lint import lint_summary
from construct2_ai_bridge.project_reader import inspect_project, load_project

EVENTS = (
    "<events>"
    '<event name="On start"><condition id="OnStart" />'
    '<action name="Set"><param name="v" value="10" /></action>'
    '<subevents><event name="Child" disabled="true"><condition id="X" /></event></subevents></event>'
    '<event name="Empty" />'
    "</events>"
)


def _summary(tmp_path: Path, xml: str = EVENTS) -> dict:
    project = tmp_path / "events.xml"
    project.write_text(xml, encoding="utf-8")
    return inspect_project(load_project(project))


def test_explain_renders_if_then_with_params_and_nesting(tmp_path: Path) -> None:
    result = explain_outlines(_summary(tmp_path)["event_outlines"])
    text = result["text"]
    assert "== events.xml ==" in text
    assert "[events.xml::event:0001] On start" in text
    assert "IF   OnStart" in text
    assert "THEN Set(v=10)" in text
    assert "  [events.xml::event:0002] Child [DISABLED]" in text
    assert "(no conditions or actions detected)" in text
    assert result["included_event_count"] == 3
    assert result["truncated"] is False


def test_explain_filters_by_event_id_and_document(tmp_path: Path) -> None:
    outlines = _summary(tmp_path)["event_outlines"]
    only = explain_outlines(outlines, event_ids={"events.xml::event:0003"})
    assert only["included_event_count"] == 1
    assert "Empty" in only["text"] and "On start" not in only["text"]
    assert explain_outlines(outlines, document="other.xml")["included_event_count"] == 0


def test_explain_respects_character_budget(tmp_path: Path) -> None:
    outlines = _summary(tmp_path)["event_outlines"]
    result = explain_outlines(outlines, max_chars=40)
    assert result["truncated"] is True
    assert result["included_event_count"] >= 1  # always at least one whole event


def test_lint_flags_empty_disabled_and_no_actions(tmp_path: Path) -> None:
    result = lint_summary(_summary(tmp_path))
    codes = {(f["code"], f["event_id"]) for f in result["findings"]}
    assert ("empty-event", "events.xml::event:0003") in codes
    assert ("disabled-event", "events.xml::event:0002") in codes
    assert ("no-actions", "events.xml::event:0002") in codes
    assert ("empty-event", "events.xml::event:0001") not in codes
    assert result["findings"][0]["severity"] == "warning"  # warnings sort first


def test_lint_unused_global_variable(tmp_path: Path) -> None:
    xml = (
        '<c2project><globalVariables><globalvar name="Score" /><globalvar name="Lives" /></globalVariables>'
        '<events><event name="x"><condition id="Compare"><param name="left" value="Score" /></condition>'
        '<action id="Do" /></event></events></c2project>'
    )
    result = lint_summary(_summary(tmp_path, xml))
    unused = [f["message"] for f in result["findings"] if f["code"] == "unused-global-variable"]
    assert unused == ["Global variable 'Lives' is not mentioned in any event outline."]


def test_lint_skips_usage_check_when_outline_truncated() -> None:
    summary = {
        "global_variables": ["Never"],
        "event_outlines": [{"document": "e.xml", "events": [], "truncated": True}],
    }
    codes = [f["code"] for f in lint_summary(summary)["findings"]]
    assert codes == ["outline-truncated"]
