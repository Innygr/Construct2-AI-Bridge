"""Read-only, best-effort inspection of Construct 2 project files."""
from __future__ import annotations
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20000

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
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data[:4096].upper():
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
                for member in members:
                    name = member.filename.replace("\\", "/")
                    if name.startswith("/") or any(part == ".." for part in name.split("/")):
                        continue
                    if member.is_dir() or not name.lower().endswith((".xml", ".caproj", ".c2proj")) or member.file_size > MAX_XML_BYTES:
                        continue
                    try:
                        data = archive.read(member)
                        _parse_xml(data, name)
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
    return tag.rsplit("}", 1)[-1].lower()

def _attr(element: ET.Element, *names: str) -> str | None:
    wanted = {n.lower() for n in names}
    for key, value in element.attrib.items():
        if _local_name(key) in wanted:
            return value
    return None

def inspect_project(document: ProjectDocument) -> dict[str, Any]:
    layouts: set[str] = set()
    event_sheets: set[str] = set()
    objects: dict[str, dict[str, Any]] = {}
    families: set[str] = set()
    global_variables: set[str] = set()
    event_count = condition_count = action_count = 0
    for label, data in document.xml_documents:
        root = _parse_xml(data, label)
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
            if tag in {"event", "block", "foreach", "for", "while", "group"}:
                event_count += 1
            elif tag == "condition":
                condition_count += 1
            elif tag == "action":
                action_count += 1
    return {
        "path": document.path, "kind": document.kind,
        "xml_document_count": len(document.xml_documents),
        "xml_documents": sorted(name for name, _ in document.xml_documents),
        "layouts": sorted(layouts), "event_sheets": sorted(event_sheets),
        "objects": sorted(objects.values(), key=lambda item: item["name"].casefold()),
        "families": sorted(families), "global_variables": sorted(global_variables),
        "counts": {"event_like_nodes": event_count, "conditions": condition_count, "actions": action_count},
        "notes": ["Inspection is best-effort; Construct 2 project XML varies by version.", "No project files were modified."]
    }
