"""Heuristic checks over an inspected project summary.

Findings are hints for a human or an AI to look at, not proof of a bug: Construct 2
XML varies by version and the event outlines are best-effort. Every finding says
which event it refers to so it can be verified in the editor.
"""
from __future__ import annotations

from typing import Any

DEEP_NESTING_DEPTH = 6
CONTAINER_KINDS = {"group"}


def _event_text(event: dict[str, Any]) -> str:
    """All searchable text of an event, lower-cased, for usage detection."""
    parts: list[str] = [str(event.get("label") or "")]
    parts.extend(str(item) for item in event.get("conditions", []))
    parts.extend(str(item) for item in event.get("actions", []))
    for key in ("condition_details", "action_details"):
        for detail in event.get(key, []):
            for field in ("name", "id", "text", "plugin"):
                if detail.get(field):
                    parts.append(str(detail[field]))
            for param in detail.get("parameters", []):
                for field in ("name", "value", "text"):
                    if param.get(field):
                        parts.append(str(param[field]))
    return " ".join(parts).lower()


def lint_summary(summary: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    outlines = summary.get("event_outlines", [])
    any_truncated = any(outline.get("truncated") for outline in outlines)

    corpus: list[str] = []
    for outline in outlines:
        for event in outline.get("events", []):
            eid = event.get("event_id")
            kind = event.get("kind")
            corpus.append(_event_text(event))
            no_conditions = event.get("condition_count", 0) == 0
            no_actions = event.get("action_count", 0) == 0
            no_children = event.get("child_event_count", 0) == 0
            if event.get("disabled"):
                findings.append({
                    "severity": "info", "code": "disabled-event", "event_id": eid,
                    "message": "Event is explicitly disabled and will not run.",
                })
            if kind not in CONTAINER_KINDS and no_conditions and no_actions and no_children:
                findings.append({
                    "severity": "warning", "code": "empty-event", "event_id": eid,
                    "message": "Event has no detected conditions, actions or sub-events.",
                })
            elif kind not in CONTAINER_KINDS and not no_conditions and no_actions and no_children:
                findings.append({
                    "severity": "warning", "code": "no-actions", "event_id": eid,
                    "message": "Event has conditions but no detected actions or sub-events.",
                })
            if event.get("depth", 0) >= DEEP_NESTING_DEPTH:
                findings.append({
                    "severity": "info", "code": "deep-nesting", "event_id": eid,
                    "message": f"Event is nested {event['depth']} levels deep; consider flattening or using a group.",
                })

    if any_truncated:
        findings.append({
            "severity": "info", "code": "outline-truncated", "event_id": None,
            "message": "At least one event outline hit the safety limit, so usage checks may miss later events.",
        })
    elif outlines:
        haystack = " ".join(corpus)
        for name in summary.get("global_variables", []):
            if name.lower() not in haystack:
                findings.append({
                    "severity": "info", "code": "unused-global-variable", "event_id": None,
                    "message": f"Global variable '{name}' is not mentioned in any event outline.",
                })

    order = {"warning": 0, "info": 1}
    findings.sort(key=lambda f: (order.get(f["severity"], 9), f["code"], f.get("event_id") or ""))
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding["code"]] = counts.get(finding["code"], 0) + 1
    return {
        "findings": findings,
        "counts": counts,
        "note": "Heuristic hints only; verify each in the Construct 2 editor before changing anything.",
    }
