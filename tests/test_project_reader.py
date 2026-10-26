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
