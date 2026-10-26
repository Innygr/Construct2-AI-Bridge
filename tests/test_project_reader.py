from pathlib import Path
import zipfile
import pytest
from construct2_ai_bridge.project_reader import ProjectReadError, inspect_project, load_project

def test_inspects_capx_xml(tmp_path: Path) -> None:
    project = tmp_path / "sample.capx"
    xml = b'<c2project><objectTypes><objectType name="Player" plugin="Sprite" /></objectTypes><layouts><layout name="Start" /></layouts><eventSheets><eventSheet name="Gameplay" /></eventSheets><globalVariables><globalvar name="Score" /></globalVariables></c2project>'
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("project.xml", xml)
    summary = inspect_project(load_project(project))
    assert summary["kind"] == "capx"
    assert "Start" in summary["layouts"]
    assert "Gameplay" in summary["event_sheets"]
    assert "Score" in summary["global_variables"]
    assert summary["objects"][0]["name"] == "Player"

def test_rejects_unsupported_extension(tmp_path: Path) -> None:
    file = tmp_path / "game.txt"
    file.write_text("nope")
    with pytest.raises(ProjectReadError, match="Unsupported"):
        load_project(file)

def test_rejects_dtd(tmp_path: Path) -> None:
    file = tmp_path / "game.caproj"
    file.write_text('<!DOCTYPE foo [<!ENTITY x "boom">]><foo>&x;</foo>')
    with pytest.raises(ProjectReadError, match="DTD/entity"):
        load_project(file)


def test_reports_missing_project_structures(tmp_path: Path) -> None:
    project = tmp_path / "minimal.caproj"
    project.write_text("<c2project><metadata /></c2project>", encoding="utf-8")
    summary = inspect_project(load_project(project))
    assert "diagnostics" in summary
    assert any("layout" in message.lower() for message in summary["diagnostics"])
    assert any("object" in message.lower() for message in summary["diagnostics"])


def test_ignores_traversal_named_xml_entries(tmp_path: Path) -> None:
    project = tmp_path / "archive.capx"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("../outside.xml", b'<layout name="ShouldNotAppear" />')
        archive.writestr("project.xml", b'<c2project><layouts><layout name="Safe" /></layouts></c2project>')

    document = load_project(project)
    summary = inspect_project(document)
    assert "Safe" in summary["layouts"]
    assert "ShouldNotAppear" not in summary["layouts"]
    assert all(".." not in name.split("/") for name in summary["xml_documents"])


def test_builds_nested_event_outline_with_conditions_and_actions(tmp_path: Path) -> None:
    project = tmp_path / "events.xml"
    project.write_text(
        '<events><event name="On start">'
        '<conditions><condition id="system-on-start" /></conditions>'
        '<actions><action name="Set score" /></actions>'
        '<subevents><event name="Nested event">'
        '<conditions><condition name="Compare score" /></conditions>'
        '</event></subevents></event></events>',
        encoding="utf-8",
    )
    summary = inspect_project(load_project(project))
    outline = summary["event_outlines"][0]
    assert outline["event_count"] == 2
    assert outline["events"][0]["label"] == "On start"
    assert outline["events"][0]["condition_count"] == 1
    assert outline["events"][0]["action_count"] == 1
    assert outline["events"][0]["child_event_count"] == 1
    assert outline["events"][1]["depth"] == 1
    assert outline["events"][1]["label"] == "Nested event"

def test_extracts_parameter_attributes_for_conditions_and_actions(tmp_path: Path) -> None:
    project = tmp_path / "parameter-events.xml"
    project.write_text(
        '<events><event name="Example">'
        '<condition id="Compare"><param name="left" value="Score" /></condition>'
        '<action name="Set"><param name="right" value="10" /></action>'
        '</event></events>',
        encoding="utf-8",
    )
    summary = inspect_project(load_project(project))
    event = summary["event_outlines"][0]["events"][0]
    assert event["condition_details"][0]["parameters"][0]["value"] == "Score"
    assert event["action_details"][0]["parameters"][0]["value"] == "10"

def test_rejects_dtd_after_long_prolog_whitespace(tmp_path: Path) -> None:
    file = tmp_path / "late-dtd.caproj"
    file.write_bytes((b" " * 5000) + b'<!DOCTYPE foo [<!ENTITY x "boom">]><foo>&x;</foo>')
    with pytest.raises(ProjectReadError, match="DTD/entity"):
        load_project(file)


def test_rejects_excessively_deep_xml(tmp_path: Path) -> None:
    file = tmp_path / "deep.caproj"
    nested = "<node>" * 130 + "</node>" * 130
    file.write_text(nested, encoding="utf-8")
    with pytest.raises(ProjectReadError, match="nesting exceeds"):
        load_project(file)


def test_recognizes_construct2_event_block_nodes(tmp_path: Path) -> None:
    project = tmp_path / "construct2-event-blocks.xml"
    project.write_text(
        '<events><event-block sid="1" name="Start event">'
        '<conditions><condition id="OnStart" /></conditions>'
        '<actions><action id="SetValue" /></actions>'
        '<subevents><event-block sid="2" name="Nested event">'
        '<conditions><condition id="Compare" /></conditions>'
        '</event-block></subevents></event-block></events>',
        encoding="utf-8",
    )
    summary = inspect_project(load_project(project))
    outline = summary["event_outlines"][0]
    assert outline["event_count"] == 2
    assert outline["events"][0]["kind"] == "eventblock"
    assert outline["events"][0]["label"] == "Start event"
    assert outline["events"][0]["condition_count"] == 1
    assert outline["events"][0]["action_count"] == 1
    assert outline["events"][1]["depth"] == 1
    assert outline["events"][1]["label"] == "Nested event"


def test_event_outline_reports_truncation_at_safety_limit(tmp_path: Path) -> None:
    from construct2_ai_bridge.project_reader import MAX_OUTLINE_EVENTS

    project = tmp_path / "many-events.xml"
    events = "".join(f'<event name="Event {index}" />' for index in range(MAX_OUTLINE_EVENTS + 1))
    project.write_text(f"<events>{events}</events>", encoding="utf-8")
    summary = inspect_project(load_project(project))
    outline = summary["event_outlines"][0]
    assert outline["event_count"] == MAX_OUTLINE_EVENTS
    assert outline["truncated"] is True



def test_event_outline_preserves_explicit_disabled_state(tmp_path: Path) -> None:
    project = tmp_path / "disabled-events.xml"
    project.write_text(
        '<events>'
        '<event name="Disabled by flag" disabled="true" />'
        '<event name="Enabled by flag" disabled="0" />'
        '<event name="Disabled by enabled flag" enabled="false" />'
        '<event name="Enabled by enabled flag" enabled="true" />'
        '<event name="Unknown state" />'
        '</events>',
        encoding="utf-8",
    )
    summary = inspect_project(load_project(project))
    events = summary["event_outlines"][0]["events"]
    assert [event.get("disabled") for event in events] == [
        True, False, True, False, None
    ]



def test_condition_and_action_details_preserve_inline_text(tmp_path: Path) -> None:
    project = tmp_path / "inline-text.xml"
    project.write_text(
        '<events><event name="Example">'
        '<condition id="Compare">Score &gt; 10</condition>'
        '<action id="Set">Set score to 20</action>'
        '</event></events>',
        encoding="utf-8",
    )
    summary = inspect_project(load_project(project))
    event = summary["event_outlines"][0]["events"][0]
    assert event["condition_details"][0]["text"] == "Score > 10"
    assert event["action_details"][0]["text"] == "Set score to 20"


def test_reports_skipped_capx_xml_entries_in_diagnostics(tmp_path: Path) -> None:
    project = tmp_path / "partial.capx"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("project.xml", b'<c2project><layouts><layout name="Safe" /></layouts></c2project>')
        archive.writestr("broken.xml", b'<c2project><layout>')
        archive.writestr("../outside.xml", b'<layout name="Unsafe" />')

    summary = inspect_project(load_project(project))
    assert "Safe" in summary["layouts"]
    assert "Unsafe" not in summary["layouts"]
    assert any("malformed or could not be read safely" in item for item in summary["diagnostics"])
    assert any("unsafe paths" in item for item in summary["diagnostics"])
