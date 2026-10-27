"""Local HTTP API and browser interface."""
import json
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from . import __version__
from .project_reader import ProjectReadError, inspect_project, load_project

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

class OpenProjectRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)

@app.get("/api/status")
def status() -> dict[str, str]:
    return {"status": "ok", "name": "Construct 2 AI Bridge", "version": __version__, "mode": "read-only"}

@app.post("/api/project/open")
def open_project(request: OpenProjectRequest) -> dict[str, Any]:
    global _current_summary
    try:
        document = load_project(request.path)
        _current_summary = inspect_project(document)
    except ProjectReadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Could not open project: {exc}") from exc
    return {"opened": True, "summary": _current_summary}

@app.get("/api/project/summary")
def project_summary() -> dict[str, Any]:
    if _current_summary is None:
        raise HTTPException(status_code=404, detail="No project is open. Use POST /api/project/open first.")
    return _current_summary


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
