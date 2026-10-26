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
    event = response.json()["event_outlines"][0]["events"][0]
    assert event["condition_count"] == 1
    assert event["action_count"] == 1
    assert event["event_index"] == 1
    assert event["event_id"] == "game.caproj::event:0001"
    assert "diagnostics" in response.json()

def test_home_page_includes_event_outline_view() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="event-outline"' in response.text
    assert "function renderOutline(summary)" in response.text
    assert "event.event_id" in response.text
    assert "Inspection note:" in response.text
    assert "DISABLED" in response.text
    assert "Prepare AI context" in response.text
    assert "Copy context" in response.text
    assert "event-context-pick" in response.text
    assert "Include in AI context" in response.text
    assert "Select at least one event" in response.text
    assert "navigator.clipboard.writeText" in response.text
    assert "Nothing is submitted automatically." in response.text
    assert "Project report (JSON)" in response.text


def test_ai_context_returns_grounded_prompt_ready_context(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    project.write_text(
        '<c2project><layouts><layout name="Start" /></layouts>'
        '<objectTypes><objectType name="Player" plugin="Sprite" /></objectTypes>'
        '<event name="On start"><conditions><condition id="start" /></conditions>'
        '<actions><action name="Set score" /></actions></event></c2project>',
        encoding="utf-8",
    )
    assert client.post("/api/project/open", json={"path": str(project)}).status_code == 200

    response = client.get("/api/ai-context")
    assert response.status_code == 200
    body = response.json()
    assert body["included_event_count"] == 1
    assert "event_id" in body["context"]
    assert "Do not invent missing conditions" in body["context"]
    assert "Player" in body["context"]


def test_ai_context_can_filter_events_and_reject_unknown_ids(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    project.write_text(
        '<c2project><event name="First" /><event name="Second" /></c2project>',
        encoding="utf-8",
    )
    assert client.post("/api/project/open", json={"path": str(project)}).status_code == 200

    selected = client.get("/api/ai-context", params={"event_ids": "game.caproj::event:0002"})
    assert selected.status_code == 200
    assert selected.json()["included_event_count"] == 1
    assert "Second" in selected.json()["context"]
    assert "First" not in selected.json()["context"]

    unknown = client.get("/api/ai-context", params={"event_ids": "not-an-event"})
    assert unknown.status_code == 400
    assert "Unknown event_id" in unknown.json()["detail"]["message"]


def test_ai_context_enforces_output_character_limit(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    project.write_text(
        '<c2project>' + ''.join(f'<event name="Event {i}" />' for i in range(40)) + '</c2project>',
        encoding="utf-8",
    )
    assert client.post("/api/project/open", json={"path": str(project)}).status_code == 200

    response = client.get("/api/ai-context", params={"max_chars": 1000})
    assert response.status_code == 200
    body = response.json()
    assert body["characters"] <= 1000
    assert body["truncated"] is True
