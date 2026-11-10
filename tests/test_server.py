from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from construct2_ai_bridge import server
from construct2_ai_bridge.coordination import CoordinationError, CoordinationStore

client = TestClient(server.app)


def setup_function() -> None:
    # The API stores the active project in module state; isolate each test.
    server._current_summary = None
    server._current_document = None


def test_status_reports_reviewed_write_mode() -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "read-write with approval"


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
    assert "Prepare debugging context" in response.text
    assert "bug-description" in response.text
    assert "BUG REPORT (user-provided)" in response.text
    assert "Copy context" in response.text
    assert "event-context-pick" in response.text
    assert "Include in AI context" in response.text
    assert "Select at least one event" in response.text
    assert "navigator.clipboard.writeText" in response.text
    assert "Nothing is submitted automatically." in response.text
    assert "Advanced: full project report (JSON)" in response.text


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

def test_extension_origin_can_call_local_api() -> None:
    response = client.get(
        "/api/status",
        headers={"Origin": "moz-extension://12345678-1234-1234-1234-123456789abc"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "moz-extension://12345678-1234-1234-1234-123456789abc"
    )


def test_untrusted_website_origin_is_not_allowed() -> None:
    response = client.get(
        "/api/status",
        headers={"Origin": "https://example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers



def test_selected_xml_endpoint_returns_complete_selected_document(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    xml = '<c2project><event name="On start"><conditions><condition id="start" /></conditions></event></c2project>'
    project.write_text(xml, encoding="utf-8")
    assert client.post("/api/project/open", json={"path": str(project)}).status_code == 200

    response = client.get("/api/project/xml", params=[("documents", "game.caproj")])
    assert response.status_code == 200
    body = response.json()
    assert body["complete"] is True
    assert body["documents"][0]["xml"] == xml
    assert body["characters"] == len(xml)


def test_selected_xml_endpoint_rejects_unknown_document(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    project.write_text("<c2project />", encoding="utf-8")
    assert client.post("/api/project/open", json={"path": str(project)}).status_code == 200

    response = client.get("/api/project/xml", params=[("documents", "not-in-project.xml")])
    assert response.status_code == 400
    assert "Unknown XML document" in response.json()["detail"]["message"]


def test_ollama_status_handles_service_not_running(monkeypatch) -> None:
    import urllib.error

    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(server.urllib.request, "urlopen", unavailable)
    response = client.get("/api/ollama/status")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["models"] == []


def test_ollama_chat_validates_prompt() -> None:
    response = client.post("/api/ollama/chat", json={"model": "qwen2.5:7b", "prompt": ""})
    assert response.status_code == 422


def test_ollama_controls_are_present_in_home_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert 'id="ollama-model"' in response.text
    assert 'id="ollama-refresh"' in response.text
    assert 'id="ollama-run"' in response.text
    assert "/api/ollama/chat" in response.text
    assert 'id="xml-editor-card"' in response.text
    assert 'id="xml-document"' in response.text
    assert 'id="xml-draft"' in response.text
    assert 'id="xml-apply"' in response.text
    assert "/api/project/write" in response.text



def test_ollama_chat_returns_local_model_response(monkeypatch) -> None:
    import io
    import json

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            return json.dumps({
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": "Check the event order."},
                "done": True,
                "eval_count": 12,
            }).encode("utf-8")

    monkeypatch.setattr(server.urllib.request, "urlopen", lambda *args, **kwargs: FakeResponse())
    response = client.post("/api/ollama/chat", json={
        "model": "qwen2.5:7b",
        "prompt": "Debug this event sheet.",
    })
    assert response.status_code == 200
    assert response.json()["response"] == "Check the event order."
    assert response.json()["model"] == "qwen2.5:7b"



def test_write_project_xml_creates_backup_and_updates_project(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    original = '<c2project><layouts><layout name="Start" /></layouts></c2project>'
    updated = '<c2project><layouts><layout name="NewRoom" /></layouts></c2project>'
    project.write_text(original, encoding="utf-8")
    opened = client.post("/api/project/open", json={"path": str(project)})
    assert opened.status_code == 200

    response = client.post("/api/project/write", json={
        "document": "game.caproj",
        "xml": updated,
        "expected_project_sha256": opened.json()["project_sha256"],
    })
    assert response.status_code == 200
    assert response.json()["written"] is True
    assert project.read_text(encoding="utf-8") == updated
    assert Path(str(project) + ".bak").read_text(encoding="utf-8") == original
    assert response.json()["summary"]["layouts"] == ["NewRoom"]


def test_write_project_xml_rejects_invalid_xml_without_touching_file(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    original = "<c2project />"
    project.write_text(original, encoding="utf-8")
    opened = client.post("/api/project/open", json={"path": str(project)})
    response = client.post("/api/project/write", json={
        "document": "game.caproj",
        "xml": "<c2project>",
        "expected_project_sha256": opened.json()["project_sha256"],
    })
    assert response.status_code == 400
    assert project.read_text(encoding="utf-8") == original
    assert not Path(str(project) + ".bak").exists()


def test_write_project_xml_rejects_stale_project_hash(tmp_path: Path) -> None:
    project = tmp_path / "game.caproj"
    project.write_text("<c2project />", encoding="utf-8")
    opened = client.post("/api/project/open", json={"path": str(project)})
    project.write_text("<c2project><external-change /></c2project>", encoding="utf-8")
    response = client.post("/api/project/write", json={
        "document": "game.caproj",
        "xml": "<c2project><our-change /></c2project>",
        "expected_project_sha256": opened.json()["project_sha256"],
    })
    assert response.status_code == 409
    assert "<external-change" in project.read_text(encoding="utf-8")


def test_write_project_xml_replaces_only_selected_capx_member(tmp_path: Path) -> None:
    import zipfile

    project = tmp_path / "game.capx"
    original_xml = b'<c2project><layouts><layout name="Start" /></layouts></c2project>'
    updated_xml = b'<c2project><layouts><layout name="NewRoom" /></layouts></c2project>'
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("project.xml", original_xml)
        archive.writestr("data.bin", b"keep-this")
    opened = client.post("/api/project/open", json={"path": str(project)})
    response = client.post("/api/project/write", json={
        "document": "project.xml",
        "xml": updated_xml.decode("utf-8"),
        "expected_project_sha256": opened.json()["project_sha256"],
    })
    assert response.status_code == 200
    with zipfile.ZipFile(project, "r") as archive:
        assert archive.read("project.xml") == updated_xml
        assert archive.read("data.bin") == b"keep-this"
    with zipfile.ZipFile(str(project) + ".bak", "r") as backup:
        assert backup.read("project.xml") == original_xml


def test_project_tree_returns_bounded_child_index_paths(tmp_path: Path) -> None:
    project = tmp_path / "tree.caproj"
    project.write_text('<c2project><layout name="Start"><layer name="World" /></layout></c2project>', encoding="utf-8")
    assert client.post("/api/project/open", json={"path": str(project)}).status_code == 200
    response = client.get("/api/project/tree", params={"document": "tree.caproj"})
    assert response.status_code == 200
    tree = response.json()["tree"]
    assert tree["tag"] == "c2project"
    assert tree["children"][0]["path"] == [0]
    assert tree["children"][0]["children"][0]["attributes"]["name"] == "World"


def test_structured_patch_updates_xml_and_creates_backup(tmp_path: Path) -> None:
    project = tmp_path / "patch.caproj"
    original = '<c2project><layout name="Start" /></c2project>'
    project.write_text(original, encoding="utf-8")
    opened = client.post("/api/project/open", json={"path": str(project)})
    response = client.post("/api/project/patch", json={
        "document": "patch.caproj",
        "expected_project_sha256": opened.json()["project_sha256"],
        "operations": [
            {"op": "set_attribute", "path": [0], "name": "name", "value": "Main"}
        ],
    })
    assert response.status_code == 200
    assert response.json()["patched"] is True
    assert response.json()["operation_count"] == 1
    assert 'name="Main"' in project.read_text(encoding="utf-8")
    assert Path(str(project) + ".bak").read_text(encoding="utf-8") == original


def test_structured_patch_rejects_root_deletion_without_writing(tmp_path: Path) -> None:
    project = tmp_path / "patch.caproj"
    original = '<c2project><layout name="Start" /></c2project>'
    project.write_text(original, encoding="utf-8")
    opened = client.post("/api/project/open", json={"path": str(project)})
    response = client.post("/api/project/patch", json={
        "document": "patch.caproj",
        "expected_project_sha256": opened.json()["project_sha256"],
        "operations": [{"op": "delete_node", "path": []}],
    })
    assert response.status_code == 400
    assert project.read_text(encoding="utf-8") == original
    assert not Path(str(project) + ".bak").exists()


def test_structured_patch_rejects_stale_project_hash(tmp_path: Path) -> None:
    project = tmp_path / "patch.caproj"
    project.write_text('<c2project />', encoding="utf-8")
    opened = client.post("/api/project/open", json={"path": str(project)})
    project.write_text('<c2project><external /></c2project>', encoding="utf-8")
    response = client.post("/api/project/patch", json={
        "document": "patch.caproj",
        "expected_project_sha256": opened.json()["project_sha256"],
        "operations": [{"op": "set_attribute", "path": [], "name": "edited", "value": "yes"}],
    })
    assert response.status_code == 409
    assert "<external" in project.read_text(encoding="utf-8")


def test_structured_patch_preserves_xml_comments(tmp_path: Path) -> None:
    project = tmp_path / "comments.caproj"
    original = '<c2project><!-- keep this note --><layout name="Start" /></c2project>'
    project.write_text(original, encoding="utf-8")
    opened = client.post("/api/project/open", json={"path": str(project)})
    response = client.post("/api/project/patch", json={
        "document": "comments.caproj",
        "expected_project_sha256": opened.json()["project_sha256"],
        "operations": [{"op": "set_attribute", "path": [1], "name": "name", "value": "Main"}],
    })
    assert response.status_code == 200
    assert "<!-- keep this note -->" in project.read_text(encoding="utf-8")


def test_coordination_tasks_claims_and_messages_are_shared(tmp_path: Path) -> None:
    store = CoordinationStore(tmp_path / "coordination.sqlite3")
    task = store.create_task("Parse event conditions", "Inspect condition nodes.", "chatgpt")
    claimed = store.claim_task(task["id"], "claude", "claude/event-parser")
    assert claimed["owner"] == "claude"
    assert claimed["branch"] == "claude/event-parser"
    with pytest.raises(CoordinationError) as conflict:
        store.claim_task(task["id"], "chatgpt", "chatgpt/parser")
    assert conflict.value.status_code == 409
    message = store.post_message("claude", "I found the condition node structure.", task["id"])
    assert message["task_id"] == task["id"]
    assert store.list_messages(task["id"])[0]["agent"] == "claude"


def test_coordination_file_locks_prevent_cross_agent_edits(tmp_path: Path) -> None:
    store = CoordinationStore(tmp_path / "coordination.sqlite3")
    lock = store.acquire_lock("src/parser.py", "claude", None, 900)
    with pytest.raises(CoordinationError) as conflict:
        store.acquire_lock("src/parser.py", "chatgpt", None, 900)
    assert conflict.value.status_code == 409
    store.release_lock("src/parser.py", "claude", lock["token"])
    assert store.list_locks() == []


def test_coordination_lock_token_is_required_to_release(tmp_path: Path) -> None:
    store = CoordinationStore(tmp_path / "coordination.sqlite3")
    store.acquire_lock("src/parser.py", "claude", None, 900)
    with pytest.raises(CoordinationError):
        store.release_lock("src/parser.py", "chatgpt", "not-the-token")
    assert len(store.list_locks()) == 1


def test_coordination_store_persists_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "coordination.sqlite3"
    first = CoordinationStore(db)
    task = first.create_task("Persist this", "", "chatgpt")
    second = CoordinationStore(db)
    assert second.list_tasks()[0]["id"] == task["id"]


def test_coordination_api_and_rejects_unsafe_lock_paths(tmp_path: Path) -> None:
    original = server._coordination
    server._coordination = CoordinationStore(tmp_path / "api.sqlite3")
    try:
        task_response = client.post("/api/coordination/tasks", json={
            "title": "Review parser",
            "description": "Check parser safety.",
            "created_by": "chatgpt",
        })
        assert task_response.status_code == 200
        task_id = task_response.json()["task"]["id"]
        claim = client.post(f"/api/coordination/tasks/{task_id}/claim", json={"agent": "claude"})
        assert claim.status_code == 200
        message = client.post("/api/coordination/messages", json={
            "agent": "claude", "task_id": task_id, "body": "Review complete.",
        })
        assert message.status_code == 200
        assert client.get("/api/coordination/messages", params={"task_id": task_id}).json()["messages"]
        unsafe = client.post("/api/coordination/locks", json={
            "path": "../server.py", "agent": "chatgpt",
        })
        assert unsafe.status_code == 400
    finally:
        server._coordination = original
