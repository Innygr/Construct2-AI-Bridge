"""Local HTTP API and browser interface."""
import json
import hashlib
import os
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from . import __version__
from .project_reader import MAX_XML_BYTES, ProjectReadError, _parse_xml, inspect_project, load_project
from .coordination import CoordinationError, CoordinationStore

app = FastAPI(title="Construct 2 AI Bridge", version=__version__)

# Browser extensions have their own origin (moz-extension:// or
# chrome-extension://). Allow those origins to call this loopback-only API;
# normal websites are not granted cross-origin access.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(moz-extension|chrome-extension)://[^/]+$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
_current_summary: dict[str, Any] | None = None
_current_document = None
_coordination = CoordinationStore()

class OpenProjectRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)


class WriteXmlRequest(BaseModel):
    agent: str = Field(default="local", min_length=1, max_length=80)
    document: str = Field(min_length=1, max_length=4096)
    xml: str = Field(min_length=1, max_length=32 * 1024 * 1024)
    expected_project_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class XmlOperation(BaseModel):
    op: str = Field(pattern=r"^(set_attribute|remove_attribute|set_text|append_xml|delete_node)$")
    path: list[int] = Field(default_factory=list, max_length=128)
    name: str | None = Field(default=None, max_length=256)
    value: str | None = Field(default=None, max_length=MAX_XML_BYTES)
    xml: str | None = Field(default=None, max_length=MAX_XML_BYTES)


class PatchXmlRequest(BaseModel):
    agent: str = Field(default="local", min_length=1, max_length=80)
    document: str = Field(min_length=1, max_length=4096)
    expected_project_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    operations: list[XmlOperation] = Field(min_length=1, max_length=100)


class OllamaChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=2_000_000)
    system: str = Field(default="You are a careful Construct 2 debugging assistant. Ground claims in supplied project evidence, distinguish observations from hypotheses, and suggest changes only.", max_length=8000)


@app.get("/api/ollama/status")
def ollama_status() -> dict[str, Any]:
    """Check the local Ollama service and list locally installed models."""
    request = urllib.request.Request("http://127.0.0.1:11434/api/tags", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            data = json.loads(response.read(2_000_000).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return {"available": False, "models": [], "message": f"Could not reach Ollama at 127.0.0.1:11434: {exc}"}
    models = [
        {"name": item.get("name", ""), "size": item.get("size")}
        for item in data.get("models", [])
        if isinstance(item, dict) and item.get("name")
    ]
    return {"available": True, "models": models, "message": "Ollama is online."}


@app.post("/api/ollama/chat")
def ollama_chat(request: OllamaChatRequest) -> dict[str, Any]:
    """Send an explicitly submitted prompt to the local Ollama instance."""
    payload = json.dumps({
        "model": request.model,
        "stream": False,
        "messages": [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.prompt},
        ],
    }).encode("utf-8")
    upstream = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(upstream, timeout=300) as response:
            result = json.loads(response.read(20_000_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read(4000).decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=f"Ollama returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not complete local Ollama request: {exc}") from exc
    message = result.get("message", {})
    return {
        "model": result.get("model", request.model),
        "response": message.get("content", "") if isinstance(message, dict) else "",
        "done": result.get("done", False),
        "total_duration": result.get("total_duration"),
        "prompt_eval_count": result.get("prompt_eval_count"),
        "eval_count": result.get("eval_count"),
    }



class CoordinationTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=12000)
    created_by: str = Field(min_length=1, max_length=80)


class CoordinationTaskClaim(BaseModel):
    agent: str = Field(min_length=1, max_length=80)
    branch: str | None = Field(default=None, max_length=200)


class CoordinationTaskUpdate(BaseModel):
    agent: str = Field(min_length=1, max_length=80)
    status: str = Field(pattern=r"^(open|claimed|in_review|done|blocked)$")
    branch: str | None = Field(default=None, max_length=200)


class CoordinationMessageCreate(BaseModel):
    agent: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=12000)
    task_id: str | None = Field(default=None, max_length=40)


class CoordinationLockCreate(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    agent: str = Field(min_length=1, max_length=80)
    task_id: str | None = Field(default=None, max_length=40)
    ttl_seconds: int = Field(default=900, ge=30, le=86400)


class CoordinationLockRelease(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    agent: str = Field(min_length=1, max_length=80)
    token: str = Field(min_length=1, max_length=64)


def _coordination_call(callback, *args, **kwargs):
    try:
        return callback(*args, **kwargs)
    except CoordinationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _assert_project_write_unlocked(document: str, project_path: Path, agent: str) -> None:
    active = _coordination.list_locks()
    protected = {document, project_path.name}
    conflicts = [lock for lock in active if lock["path"] in protected and lock["agent"] != agent]
    if conflicts:
        owner = conflicts[0]["agent"]
        raise HTTPException(status_code=409, detail=f"Project file is locked by {owner}; wait for the lock to expire or be released.")


def _validate_lock_path(path: str) -> str:
    from pathlib import PurePosixPath
    normalized = path.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if parsed.is_absolute() or not parsed.parts or any(part in ("", ".", "..") for part in parsed.parts):
        raise HTTPException(status_code=400, detail="Lock paths must be safe project-relative paths.")
    return parsed.as_posix()


@app.get("/api/coordination/status")
def coordination_status() -> dict[str, Any]:
    return {"available": True, "storage": "sqlite", "agent_protocol": "poll-and-publish", "agents_are_autonomous": False}


@app.get("/api/coordination/tasks")
def coordination_tasks(status: str | None = Query(default=None, pattern=r"^(open|claimed|in_review|done|blocked)$")) -> dict[str, Any]:
    return {"tasks": _coordination.list_tasks(status)}


@app.post("/api/coordination/tasks")
def coordination_create_task(request: CoordinationTaskCreate) -> dict[str, Any]:
    return {"task": _coordination.create_task(request.title, request.description, request.created_by)}


@app.post("/api/coordination/tasks/{task_id}/claim")
def coordination_claim_task(task_id: str, request: CoordinationTaskClaim) -> dict[str, Any]:
    return {"task": _coordination_call(_coordination.claim_task, task_id, request.agent, request.branch)}


@app.patch("/api/coordination/tasks/{task_id}")
def coordination_update_task(task_id: str, request: CoordinationTaskUpdate) -> dict[str, Any]:
    return {"task": _coordination_call(_coordination.update_task, task_id, request.agent, request.status, request.branch)}


@app.get("/api/coordination/messages")
def coordination_messages(
    task_id: str | None = Query(default=None, max_length=40),
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    return {"messages": _coordination.list_messages(task_id, after_id, limit)}


@app.post("/api/coordination/messages")
def coordination_post_message(request: CoordinationMessageCreate) -> dict[str, Any]:
    return {"message": _coordination_call(_coordination.post_message, request.agent, request.body, request.task_id)}


@app.get("/api/coordination/locks")
def coordination_locks() -> dict[str, Any]:
    return {"locks": _coordination.list_locks()}


@app.post("/api/coordination/locks")
def coordination_acquire_lock(request: CoordinationLockCreate) -> dict[str, Any]:
    path = _validate_lock_path(request.path)
    return {"lock": _coordination_call(_coordination.acquire_lock, path, request.agent, request.task_id, request.ttl_seconds)}


@app.delete("/api/coordination/locks")
def coordination_release_lock(request: CoordinationLockRelease) -> dict[str, bool]:
    path = _validate_lock_path(request.path)
    _coordination_call(_coordination.release_lock, path, request.agent, request.token)
    return {"released": True}


@app.get("/api/status")
def status() -> dict[str, str]:
    return {"status": "ok", "name": "Construct 2 AI Bridge", "version": __version__, "mode": "read-write with approval"}

@app.post("/api/project/open")
def open_project(request: OpenProjectRequest) -> dict[str, Any]:
    global _current_summary, _current_document
    try:
        document = load_project(request.path)
        _current_document = document
        _current_summary = inspect_project(document)
    except ProjectReadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Could not open project: {exc}") from exc
    return {"opened": True, "summary": _current_summary, "project_sha256": _file_sha256(Path(document.path))}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@app.post("/api/project/write")
def write_project_xml(request: WriteXmlRequest) -> dict[str, Any]:
    """Apply one explicitly approved XML document update with backup and atomic replacement."""
    global _current_document, _current_summary
    _require_project()
    if _current_document is None:
        raise HTTPException(status_code=404, detail="No project XML is loaded.")
    project_path = Path(_current_document.path)
    _assert_project_write_unlocked(request.document, project_path, request.agent)
    if len(request.xml.encode("utf-8")) > MAX_XML_BYTES:
        raise HTTPException(status_code=413, detail="Updated XML exceeds the per-document size limit.")
    try:
        new_bytes = request.xml.encode("utf-8")
        _parse_xml(new_bytes, request.document)
    except (UnicodeEncodeError, ProjectReadError) as exc:
        raise HTTPException(status_code=400, detail=f"Updated XML is not valid safe XML: {exc}") from exc
    available = dict(_current_document.xml_documents)
    if request.document not in available:
        raise HTTPException(status_code=400, detail=f"Unknown XML document: {request.document}")
    current_hash = _file_sha256(project_path)
    if current_hash != request.expected_project_sha256:
        raise HTTPException(status_code=409, detail="Project changed on disk since it was loaded. Reload it before applying edits.")
    backup_path = project_path.with_name(project_path.name + ".bak")
    suffix = 1
    while backup_path.exists():
        backup_path = project_path.with_name(project_path.name + f".bak.{suffix}")
        suffix += 1
    temp_path = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{project_path.stem}.", suffix=project_path.suffix, dir=project_path.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        if _current_document.kind == "capx":
            replacements = 0
            with zipfile.ZipFile(project_path, "r") as source, zipfile.ZipFile(temp_path, "w") as target:
                target.comment = source.comment
                for info in source.infolist():
                    if info.filename == request.document:
                        target.writestr(info, new_bytes)
                        replacements += 1
                    else:
                        target.writestr(info, source.read(info))
            if replacements != 1:
                raise ProjectReadError("The selected archive document was missing or duplicated; no changes were applied.")
        else:
            if request.document != project_path.name:
                raise ProjectReadError("The selected XML document does not match the open project file.")
            temp_path.write_bytes(new_bytes)
        validated = load_project(str(temp_path))
        if _file_sha256(project_path) != request.expected_project_sha256:
            raise HTTPException(status_code=409, detail="Project changed while the edit was being prepared. No changes were applied.")
        shutil.copy2(project_path, backup_path)
        shutil.copystat(project_path, temp_path)
        os.replace(temp_path, project_path)
        temp_path = None
        validated.path = str(project_path)
        _current_document = validated
        _current_summary = inspect_project(validated)
        return {
            "written": True,
            "document": request.document,
            "backup": str(backup_path),
            "project_sha256": _file_sha256(project_path),
            "summary": _current_summary,
            "note": "Approved XML saved. A .bak backup was created before replacement.",
        }
    except HTTPException:
        raise
    except (OSError, zipfile.BadZipFile, ProjectReadError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not safely apply XML update: {exc}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)



def _get_xml_node(root: ET.Element, path: list[int]) -> ET.Element:
    node = root
    for index in path:
        children = list(node)
        if index < 0 or index >= len(children):
            raise ValueError(f"Node path {path} is invalid at child index {index}.")
        node = children[index]
    return node


def _xml_tree(root: ET.Element, max_nodes: int = 1000) -> dict[str, Any]:
    count = 0
    def build(node: ET.Element, path: list[int], depth: int) -> dict[str, Any]:
        nonlocal count
        count += 1
        if count > max_nodes:
            raise ValueError(f"XML tree exceeds the {max_nodes}-node display limit.")
        result: dict[str, Any] = {
            "path": path,
            "tag": node.tag if isinstance(node.tag, str) else ("#comment" if node.tag is ET.Comment else "#processing-instruction"),
            "attributes": dict(node.attrib),
            "text": (node.text or "").strip()[:500],
            "children": [],
        }
        if depth < 64:
            for index, child in enumerate(list(node)):
                if count >= max_nodes:
                    result["truncated"] = True
                    break
                result["children"].append(build(child, path + [index], depth + 1))
        elif list(node):
            result["truncated"] = True
        return result
    return build(root, [], 0)


@app.get("/api/project/tree")
def project_xml_tree(document: str = Query(..., min_length=1, max_length=4096)) -> dict[str, Any]:
    _require_project()
    if _current_document is None:
        raise HTTPException(status_code=404, detail="No project XML is loaded.")
    available = dict(_current_document.xml_documents)
    if document not in available:
        raise HTTPException(status_code=400, detail=f"Unknown XML document: {document}")
    try:
        root = _parse_xml(available[document], document)
        return {"document": document, "tree": _xml_tree(root), "project_sha256": _file_sha256(Path(_current_document.path))}
    except (ProjectReadError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/project/patch")
def patch_project_xml(request: PatchXmlRequest) -> dict[str, Any]:
    """Apply small, explicit structural XML operations through the normal backup/write path."""
    if _current_document is None:
        raise HTTPException(status_code=404, detail="No project XML is loaded.")
    available = dict(_current_document.xml_documents)
    if request.document not in available:
        raise HTTPException(status_code=400, detail=f"Unknown XML document: {request.document}")
    try:
        source_bytes = available[request.document]
        _parse_xml(source_bytes, request.document)  # Apply the same DTD, size, and depth checks as normal project reads.
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(source_bytes, parser=parser)
        for operation in request.operations:
            node = _get_xml_node(root, operation.path)
            if not isinstance(node.tag, str):
                raise ValueError("XML comments and processing instructions cannot be edited as elements.")
            if operation.op == "set_attribute":
                if not operation.name or operation.value is None:
                    raise ValueError("set_attribute requires name and value.")
                node.set(operation.name, operation.value)
            elif operation.op == "remove_attribute":
                if not operation.name:
                    raise ValueError("remove_attribute requires name.")
                if operation.name not in node.attrib:
                    raise ValueError(f"Attribute {operation.name!r} does not exist at {operation.path}.")
                del node.attrib[operation.name]
            elif operation.op == "set_text":
                node.text = operation.value or ""
            elif operation.op == "append_xml":
                if not operation.xml:
                    raise ValueError("append_xml requires an XML fragment.")
                fragment = _parse_xml(operation.xml.encode("utf-8"), "patch fragment")
                node.append(fragment)
            elif operation.op == "delete_node":
                if not operation.path:
                    raise ValueError("Deleting the document root is not allowed.")
                parent = _get_xml_node(root, operation.path[:-1])
                parent.remove(node)
        candidate = ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")
        write_result = write_project_xml(WriteXmlRequest(
            agent=request.agent,
            document=request.document,
            xml=candidate,
            expected_project_sha256=request.expected_project_sha256,
        ))
        return {"patched": True, "operation_count": len(request.operations), **write_result}
    except HTTPException:
        raise
    except (ValueError, ProjectReadError, ET.ParseError) as exc:
        raise HTTPException(status_code=400, detail=f"Patch rejected: {exc}") from exc


@app.get("/api/project/summary")
def project_summary() -> dict[str, Any]:
    if _current_summary is None:
        raise HTTPException(status_code=404, detail="No project is open. Use POST /api/project/open first.")
    return _current_summary


@app.get("/api/project/xml")
def selected_sheet_xml(documents: list[str] = Query(..., min_length=1)) -> dict[str, Any]:
    """Return complete XML text for explicitly selected project XML documents."""
    _require_project()
    if _current_document is None:
        raise HTTPException(status_code=404, detail="No project XML is loaded.")
    available = dict(_current_document.xml_documents)
    unknown = sorted(set(documents) - set(available))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"message": "Unknown XML document name(s).", "unknown_documents": unknown},
        )
    selected = []
    for name in documents:
        data = available[name]
        try:
            xml_text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                xml_text = data.decode("utf-16")
            except UnicodeDecodeError:
                xml_text = data.decode("utf-8", errors="replace")
        selected.append({"document": name, "xml": xml_text, "characters": len(xml_text)})
    return {
        "documents": selected,
        "document_count": len(selected),
        "characters": sum(item["characters"] for item in selected),
        "complete": True,
        "note": "Full XML for selected documents; no event outline or character truncation was applied.",
    }

@app.get("/api/ai-context")
def ai_context(
    event_ids: list[str] | None = Query(default=None),
    max_chars: int = Query(default=12000, ge=1000, le=40000),
) -> dict[str, Any]:
    """Return bounded, prompt-ready project context without sending it anywhere."""
    summary = _require_project()
    all_outlines = summary.get("event_outlines", [])
    available_events = [
        event
        for outline in all_outlines
        for event in outline.get("events", [])
    ]
    if event_ids:
        wanted = set(event_ids)
        found = {event.get("event_id") for event in available_events}
        unknown = sorted(wanted - found)
        if unknown:
            raise HTTPException(
                status_code=400,
                detail={"message": "Unknown event_id value(s).", "unknown_event_ids": unknown},
            )
        selected_events = [
            event for event in available_events if event.get("event_id") in wanted
        ]
    else:
        selected_events = available_events

    payload: dict[str, Any] = {
        "purpose": "Evidence-only context for debugging a Construct 2 project.",
        "instructions": [
            "Treat this as a best-effort inspection, not a complete or authoritative representation.",
            "Ground claims in the supplied fields and cite event_id values when discussing events.",
            "Do not invent missing conditions, actions, object properties, or runtime behavior.",
            "If the evidence is insufficient, say what additional project detail is needed.",
            "Suggest changes only; do not claim project files were modified.",
        ],
        "project": {
            "kind": summary.get("kind"),
            "xml_document_count": summary.get("xml_document_count"),
            "layouts": summary.get("layouts", []),
            "event_sheets": summary.get("event_sheets", []),
            "objects": summary.get("objects", []),
            "families": summary.get("families", []),
            "global_variables": summary.get("global_variables", []),
            "counts": summary.get("counts", {}),
            "diagnostics": summary.get("diagnostics", []),
        },
        "event_outlines": selected_events,
        "truncated": False,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    while len(rendered) > max_chars and payload["event_outlines"]:
        payload["event_outlines"].pop()
        payload["truncated"] = True
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if len(rendered) > max_chars:
        payload["project"] = {
            "kind": summary.get("kind"),
            "diagnostics": summary.get("diagnostics", []),
        }
        payload["event_outlines"] = []
        payload["truncated"] = True
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    return {
        "context": rendered,
        "characters": len(rendered),
        "max_chars": max_chars,
        "truncated": payload["truncated"],
        "included_event_count": len(payload["event_outlines"]),
    }

@app.get("/api/objects")
def objects() -> dict[str, Any]:
    summary = _require_project()
    return {key: summary[key] for key in ("objects", "families", "global_variables")}

@app.get("/api/events")
def events() -> dict[str, Any]:
    summary = _require_project()
    return {
        "event_sheets": summary["event_sheets"],
        "counts": summary["counts"],
        "event_outlines": summary.get("event_outlines", []),
        "diagnostics": summary.get("diagnostics", []),
        "note": "Event outlines are best-effort XML summaries and may not represent every Construct 2 version's event tree exactly. Check diagnostics for skipped archive entries or structures the parser did not detect.",
    }

def _require_project() -> dict[str, Any]:
    if _current_summary is None:
        raise HTTPException(status_code=404, detail="No project is open. Use POST /api/project/open first.")
    return _current_summary

@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
