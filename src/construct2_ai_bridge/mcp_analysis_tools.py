"""Read-only analysis tools for the MCP adapter: explain_events and lint_project.

Self-contained and SDK-agnostic: it never imports ``mcp``; it only needs an object
with a ``tool()`` decorator and a function that fetches JSON from the local bridge.
It uses data the bridge already serves (``/api/events`` and ``/api/objects``), so the
bridge server itself needs no changes. Both tools are read-only.

To enable, add one line to mcp_adapter.py after ``_request`` is defined:

    from .mcp_analysis_tools import register as _register_analysis_tools
    _register_analysis_tools(mcp, _request)
"""
from __future__ import annotations

from typing import Any, Callable

from .explain import explain_outlines
from .lint import lint_summary

MAX_EVENT_IDS = 100
MIN_CHARS, MAX_CHARS = 1000, 40000

Request = Callable[..., dict[str, Any]]


def build_tools(request: Request) -> dict[str, Callable[..., dict[str, Any]]]:
    """Return the tool functions bound to ``request`` (a bridge JSON fetcher)."""

    def explain_events(
        event_ids: list[str] | None = None,
        document: str | None = None,
        max_chars: int = 12000,
    ) -> dict[str, Any]:
        """Render events as compact, readable IF/THEN pseudo-code (best-effort, from the project XML only).

        Optionally limit to specific event_ids or one XML document. Output is capped
        at max_chars (1000-40000); when it is cut, narrow with event_ids or document.
        """
        if not MIN_CHARS <= max_chars <= MAX_CHARS:
            raise ValueError(f"max_chars must be between {MIN_CHARS} and {MAX_CHARS}.")
        if event_ids is not None and not 1 <= len(event_ids) <= MAX_EVENT_IDS:
            raise ValueError(f"Supply between 1 and {MAX_EVENT_IDS} event_ids, or omit event_ids.")
        data = request("/api/events")
        outlines = data.get("event_outlines", [])
        if event_ids is not None:
            known = {e.get("event_id") for o in outlines for e in o.get("events", [])}
            missing = sorted(set(event_ids) - known)
            if missing:
                raise ValueError("Unknown event_id value(s): " + ", ".join(missing))
        result = explain_outlines(
            outlines,
            document=document,
            event_ids=set(event_ids) if event_ids is not None else None,
            max_chars=max_chars,
        )
        return {
            **result,
            "note": data.get("note"),
            "hint": "Output was truncated; narrow with event_ids or document." if result["truncated"] else None,
        }

    def lint_project() -> dict[str, Any]:
        """Heuristic hints about the open project: empty events, events with no actions,
        disabled events, deep nesting and unused global variables. Hints, not proof of bugs."""
        events = request("/api/events")
        objects = request("/api/objects")
        return lint_summary({
            "event_outlines": events.get("event_outlines", []),
            "global_variables": objects.get("global_variables", []),
        })

    return {"explain_events": explain_events, "lint_project": lint_project}


def register(mcp: Any, request: Request) -> list[str]:
    """Register the tools on ``mcp`` (anything with a ``tool()`` decorator); return their names."""
    tools = build_tools(request)
    for function in tools.values():
        mcp.tool()(function)
    return list(tools)
