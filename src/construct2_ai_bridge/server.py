"""Local HTTP API and browser interface."""
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from . import __version__
from .project_reader import ProjectReadError, inspect_project, load_project

app = FastAPI(title="Construct 2 AI Bridge", version=__version__)
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

@app.get("/api/objects")
def objects() -> dict[str, Any]:
    summary = _require_project()
    return {key: summary[key] for key in ("objects", "families", "global_variables")}

@app.get("/api/events")
def events() -> dict[str, Any]:
    summary = _require_project()
    return {"event_sheets": summary["event_sheets"], "counts": summary["counts"],
            "note": "Full event-tree parsing is planned for a later inspector iteration."}

def _require_project() -> dict[str, Any]:
    if _current_summary is None:
        raise HTTPException(status_code=404, detail="No project is open. Use POST /api/project/open first.")
    return _current_summary

@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
