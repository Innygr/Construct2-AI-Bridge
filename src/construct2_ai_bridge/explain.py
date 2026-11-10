"""Turn heuristic event outlines into compact, readable pseudo-code.

The JSON event outlines are precise but verbose. This renders them as an indented
IF / THEN listing that is far cheaper to paste into an AI chat and easier for a
person to scan. It only restates what the outline already contains; it never
invents conditions, actions or behaviour.
"""
from __future__ import annotations

from typing import Any

MAX_PARAM_CHARS = 60


def _describe_node(detail: dict[str, Any]) -> str:
    """One-line description of a condition or action detail record."""
    head = (
        detail.get("name")
        or detail.get("id")
        or detail.get("type")
        or detail.get("kind")
        or "?"
    )
    plugin = detail.get("plugin")
    if plugin and plugin != head:
        head = f"{plugin}.{head}"
    pieces: list[str] = []
    for param in detail.get("parameters", []):
        key = param.get("name") or param.get("id") or param.get("type")
        value = param.get("value", param.get("text"))
        if value is None:
            continue
        value = str(value)
        if len(value) > MAX_PARAM_CHARS:
            value = value[: MAX_PARAM_CHARS - 1] + "…"
        pieces.append(f"{key}={value}" if key else value)
    text = detail.get("text")
    if text and not pieces:
        pieces.append(str(text)[:MAX_PARAM_CHARS])
    return f"{head}({', '.join(pieces)})" if pieces else str(head)


def explain_event(event: dict[str, Any]) -> list[str]:
    """Render one outline event as indented lines."""
    indent = "  " * int(event.get("depth", 0))
    title = event.get("label") or event.get("kind") or "event"
    flags = " [DISABLED]" if event.get("disabled") else ""
    lines = [f"{indent}[{event.get('event_id')}] {title}{flags}"]
    conditions = event.get("condition_details") or []
    actions = event.get("action_details") or []
    for detail in conditions:
        lines.append(f"{indent}  IF   {_describe_node(detail)}")
    shown_c = len(conditions)
    total_c = int(event.get("condition_count", shown_c))
    if total_c > shown_c:
        lines.append(f"{indent}  IF   … {total_c - shown_c} more condition(s) not shown")
    for detail in actions:
        lines.append(f"{indent}  THEN {_describe_node(detail)}")
    shown_a = len(actions)
    total_a = int(event.get("action_count", shown_a))
    if total_a > shown_a:
        lines.append(f"{indent}  THEN … {total_a - shown_a} more action(s) not shown")
    if not conditions and not actions:
        lines.append(f"{indent}  (no conditions or actions detected)")
    return lines


def explain_outlines(
    outlines: list[dict[str, Any]],
    *,
    document: str | None = None,
    event_ids: set[str] | None = None,
    max_chars: int | None = None,
) -> dict[str, Any]:
    """Render outlines to text.

    ``document`` limits output to one XML document; ``event_ids`` limits it to
    specific events; ``max_chars`` stops rendering whole events once the budget is
    reached and reports ``truncated``.
    """
    lines: list[str] = []
    included = 0
    truncated = False
    size = 0
    for outline in outlines:
        name = outline.get("document")
        if document is not None and name != document:
            continue
        events = [
            event
            for event in outline.get("events", [])
            if event_ids is None or event.get("event_id") in event_ids
        ]
        if not events:
            continue
        header = f"== {name} =="
        block_lines = [header]
        for event in events:
            rendered = explain_event(event)
            cost = sum(len(line) + 1 for line in rendered)
            if max_chars is not None and size + cost > max_chars and included > 0:
                truncated = True
                break
            block_lines.extend(rendered)
            size += cost
            included += 1
        lines.extend(block_lines)
        if outline.get("truncated"):
            lines.append("(outline hit the safety limit; later events are not listed)")
            truncated = True
        if truncated:
            break
    text = "\n".join(lines)
    return {"text": text, "characters": len(text), "included_event_count": included, "truncated": truncated}
