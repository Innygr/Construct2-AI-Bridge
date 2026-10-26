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
