from pathlib import Path

from fastapi.testclient import TestClient

from construct2_ai_bridge import server

client = TestClient(server.app)


def setup_function() -> None:
    # The API stores the active project in module state; isolate each test.
    server._current_summary = None


def test_status_reports_read_only_mode() -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "read-only"


def test_summary_requires_open_project() -> None:
    response = client.get("/api/project/summary")
    assert response.status_code == 404
    assert "No project is open" in response.json()["detail"]


def test_open_project_and_read_object_summary(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    project.write_text(
        '<c2project><objectTypes><objectType name="Player" plugin="Sprite" />'
        '</objectTypes><layouts><layout name="Start" /></layouts></c2project>',
        encoding="utf-8",
    )

    response = client.post("/api/project/open", json={"path": str(project)})
    assert response.status_code == 200
    assert response.json()["opened"] is True
    assert response.json()["summary"]["layouts"] == ["Start"]

    objects = client.get("/api/objects")
    assert objects.status_code == 200
    assert objects.json()["objects"][0]["name"] == "Player"


def test_open_missing_file_returns_client_error(tmp_path: Path) -> None:
    response = client.post(
        "/api/project/open",
        json={"path": str(tmp_path / "missing.caproj")},
    )
    assert response.status_code == 400
    assert "existing file" in response.json()["detail"]


def test_events_endpoint_explains_current_scope(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    project.write_text(
        '<c2project><eventSheets><eventSheet name="Gameplay" /></eventSheets>'
        '<event name="On start"><conditions><condition id="start" /></conditions>'
        '<actions><action name="Set score" /></actions></event></c2project>',
        encoding="utf-8",
    )
    assert client.post("/api/project/open", json={"path": str(project)}).status_code == 200

    response = client.get("/api/events")
    assert response.status_code == 200
    assert response.json()["event_sheets"] == ["Gameplay"]
    assert "best-effort" in response.json()["note"]
    assert response.json()["event_outlines"][0]["event_count"] == 1
    assert response.json()["event_outlines"][0]["events"][0]["condition_count"] == 1
    assert response.json()["event_outlines"][0]["events"][0]["action_count"] == 1

def test_home_page_includes_event_outline_view() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="event-outline"' in response.text
    assert "function renderOutline(summary)" in response.text
    assert "Project report (JSON)" in response.text
