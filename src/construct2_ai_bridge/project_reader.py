"""Read-only, best-effort inspection of Construct 2 project files."""
from __future__ import annotations
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 32 * 1024 * 1024
MAX_TOTAL_XML_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20000
MAX_OUTLINE_EVENTS = 1000
EVENT_TAGS = {"event", "block", "foreach", "for", "while", "group"}

class ProjectReadError(ValueError):
    """Raised when a project cannot be safely inspected."""

@dataclass
class ProjectDocument:
    path: str
    kind: str
    xml_documents: list[tuple[str, bytes]]

def _parse_xml(data: bytes, label: str) -> ET.Element:
    if len(data) > MAX_XML_BYTES:
        raise ProjectReadError(f"XML file is too large to inspect: {label}")
    # Scan the entire bounded document: a legal prolog can contain long whitespace/comments.
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ProjectReadError(f"DTD/entity declarations are not allowed: {label}")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ProjectReadError(f"Invalid XML in {label}: {exc}") from exc

def load_project(project_path: str | os.PathLike[str]) -> ProjectDocument:
    path = Path(project_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ProjectReadError("Project path must point to an existing file.")
    suffix = path.suffix.lower()
    if suffix == ".capx":
        docs: list[tuple[str, bytes]] = []
        try:
            with zipfile.ZipFile(path, "r") as archive:
                members = archive.infolist()
                if len(members) > MAX_ARCHIVE_MEMBERS:
                    raise ProjectReadError("Project archive contains too many entries.")
                total_xml_bytes = 0
                for member in members:
                    name = member.filename.replace("\\", "/")
                    if name.startswith("/") or any(part == ".." for part in name.split("/")):
                        continue
                    if member.is_dir() or not name.lower().endswith((".xml", ".caproj", ".c2proj")) or member.file_size > MAX_XML_BYTES:
                        continue
                    # Bound aggregate XML memory use, not just each individual entry.
                    if total_xml_bytes + member.file_size > MAX_TOTAL_XML_BYTES:
                        continue
                    try:
                        data = archive.read(member)
                        _parse_xml(data, name)
                        total_xml_bytes += len(data)
                    except (OSError, zipfile.BadZipFile, RuntimeError, ProjectReadError):
                        continue
                    docs.append((name, data))
        except (zipfile.BadZipFile, OSError) as exc:
            raise ProjectReadError(f"Could not read .capx archive: {exc}") from exc
        if not docs:
            raise ProjectReadError("No readable XML documents were found inside this .capx file.")
        return ProjectDocument(str(path), "capx", docs)
    if suffix in {".caproj", ".c2proj", ".xml"}:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ProjectReadError(f"Could not read project file: {exc}") from exc
        _parse_xml(data, str(path))
        return ProjectDocument(str(path), "xml", [(path.name, data)])
    raise ProjectReadError("Unsupported file type. Choose a .capx, .caproj, .c2proj, or XML file.")

def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower().replace("-", "").replace("_", "")

def _attr(element: ET.Element, *names: str) -> str | None:
    wanted = {n.lower() for n in names}
    for key, value in element.attrib.items():
        if _local_name(key) in wanted:
            return value
    return None

def _display_label(element: ET.Element) -> str | None:
    """Return a short, useful label without assuming a particular C2 XML schema."""
    for key in ("name", "description", "type", "id"):
        value = _attr(element, key)
        if value:
            return value[:160]
    return None

def _node_summary(element: ET.Element) -> dict[str, Any]:
    """Extract a compact, schema-agnostic description of a condition or action."""
    details: dict[str, Any] = {"kind": _local_name(element.tag)}
    for key in ("name", "id", "type", "plugin", "sid"):
        value = _attr(element, key)
        if value:
            details[key] = value[:160]
    params: list[dict[str, str]] = []
    for child in element.iter():
        if child is element or _local_name(child.tag) not in {"param", "parameter"}:
            continue
        param: dict[str, str] = {}
        for key in ("name", "id", "type", "value", "sid"):
            value = _attr(child, key)
            if value:
                param[key] = value[:160]
        text_value = (child.text or "").strip()
        if text_value:
            param["text"] = text_value[:160]
        if param:
            params.append(param)
        if len(params) >= 32:
            break
    if params:
        details["parameters"] = params
    return details

def _event_outline(root: ET.Element, document_name: str) -> dict[str, Any]:
    """Build a bounded, schema-agnostic event outline for inspection and AI context."""
    events: list[dict[str, Any]] = []
    truncated = False

    def walk(parent: ET.Element, depth: int) -> None:
        nonlocal truncated
        for child in list(parent):
            tag = _local_name(child.tag)
            if tag in EVENT_TAGS:
                if len(events) >= MAX_OUTLINE_EVENTS:
                    truncated = True
                    return
                condition_nodes: list[ET.Element] = []
                action_nodes: list[ET.Element] = []
                nested_events: list[ET.Element] = []

                def collect(node: ET.Element) -> None:
                    for descendant in list(node):
                        descendant_tag = _local_name(descendant.tag)
                        if descendant_tag in EVENT_TAGS:
                            nested_events.append(descendant)
                        elif descendant_tag == "condition":
                            condition_nodes.append(descendant)
                        elif descendant_tag == "action":
                            action_nodes.append(descendant)
                        else:
                            collect(descendant)

                collect(child)
                events.append({
                    "depth": depth,
                    "kind": tag,
                    "label": _display_label(child),
                    "conditions": [ _display_label(node) or "condition" for node in condition_nodes[:100] ],
                    "actions": [ _display_label(node) or "action" for node in action_nodes[:100] ],
                    "condition_details": [_node_summary(node) for node in condition_nodes[:100]],
                    "action_details": [_node_summary(node) for node in action_nodes[:100]],
                    "condition_count": len(condition_nodes),
                    "action_count": len(action_nodes),
                    "child_event_count": len(nested_events),
                })
                for nested in nested_events:
                    walk_nested(nested, depth + 1)
                    if truncated:
                        return
            else:
                walk(child, depth)
                if truncated:
                    return

    def walk_nested(event: ET.Element, depth: int) -> None:
        # Reuse the same collector by placing this event beneath a temporary wrapper.
        wrapper = ET.Element("outline-root")
        wrapper.append(event)
        walk(wrapper, depth)

    walk(root, 0)
    return {
        "document": document_name,
        "root_tag": _local_name(root.tag),
        "event_count": len(events),
        "events": events,
        "truncated": truncated,
    }

def inspect_project(document: ProjectDocument) -> dict[str, Any]:
    layouts: set[str] = set()
    event_sheets: set[str] = set()
    objects: dict[str, dict[str, Any]] = {}
    families: set[str] = set()
    global_variables: set[str] = set()
    event_count = condition_count = action_count = 0
    event_outlines: list[dict[str, Any]] = []
    for label, data in document.xml_documents:
        root = _parse_xml(data, label)
        event_outlines.append(_event_outline(root, label))
        for element in root.iter():
            tag, name = _local_name(element.tag), _attr(element, "name")
            if name:
                if tag == "layout":
                    layouts.add(name)
                elif tag in {"eventsheet", "eventsheetref"}:
                    event_sheets.add(name)
                elif tag in {"family", "objectfamily"}:
                    families.add(name)
                elif tag in {"globalvar", "globalvariable", "variable"}:
                    global_variables.add(name)
                elif tag in {"objecttype", "object"}:
                    objects[name] = {"name": name, "plugin": _attr(element, "plugin", "type")}
            if tag in EVENT_TAGS:
                event_count += 1
            elif tag == "condition":
                condition_count += 1
            elif tag == "action":
                action_count += 1
    diagnostics: list[str] = []
    if not layouts:
        diagnostics.append("No layout elements were detected in the readable XML documents.")
    if not event_sheets:
        diagnostics.append("No event-sheet elements were detected in the readable XML documents.")
    if not objects:
        diagnostics.append("No object types were detected in the readable XML documents.")
    if not global_variables:
        diagnostics.append("No global variables were detected; the project may not define any, or this XML layout was not recognized.")
    return {
        "path": document.path, "kind": document.kind,
        "xml_document_count": len(document.xml_documents),
        "xml_documents": sorted(name for name, _ in document.xml_documents),
        "layouts": sorted(layouts), "event_sheets": sorted(event_sheets),
        "objects": sorted(objects.values(), key=lambda item: item["name"].casefold()),
        "families": sorted(families), "global_variables": sorted(global_variables),
        "counts": {"event_like_nodes": event_count, "conditions": condition_count, "actions": action_count},
        "event_outlines": event_outlines,
        "diagnostics": diagnostics,
        "notes": ["Inspection is best-effort; Construct 2 project XML varies by version.", "Event outlines are heuristic summaries, not a lossless event-sheet representation.", "No project files were modified."]
    }
