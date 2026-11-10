"""List and restore the numbered .bak backups the write workflow creates.

The write endpoint saves ``<project>.bak``, then ``.bak.1``, ``.bak.2`` ... before
replacing a project, but gives no way back. This module adds that, with the same
care as writing: the backup must still be a safe, readable project, the project
must not have changed since the caller looked at it, the current file is itself
backed up first (so a restore can be undone), and the swap is atomic.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .project_reader import ProjectReadError, load_project


class BackupError(Exception):
    """A backup operation was refused; ``status_code`` mirrors the HTTP meaning."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pattern(project_path: Path) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(project_path.name)}\.bak(?:\.(\d+))?$")


def next_backup_path(project_path: Path) -> Path:
    """Next unused backup name, using the same scheme as the write endpoint."""
    candidate = project_path.with_name(project_path.name + ".bak")
    suffix = 1
    while candidate.exists():
        candidate = project_path.with_name(project_path.name + f".bak.{suffix}")
        suffix += 1
    return candidate


def list_backups(project_path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Backups of ``project_path``, oldest first (``.bak`` then ``.bak.1``, ``.bak.2`` ...).

    Only regular files whose names match exactly are listed; symlinks and look-alike
    names (``game.caproj.bak.txt``, another project's backup) are ignored.
    """
    project = Path(project_path).expanduser().resolve()
    pattern = _pattern(project)
    found: list[tuple[int, Path]] = []
    try:
        entries = list(project.parent.iterdir())
    except OSError as exc:
        raise BackupError(f"Could not read the project folder: {exc}") from exc
    for entry in entries:
        match = pattern.match(entry.name)
        if match and entry.is_file() and not entry.is_symlink():
            found.append((int(match.group(1) or 0), entry))
    found.sort(key=lambda item: item[0])
    rows: list[dict[str, Any]] = []
    for index, entry in found:
        stat = entry.stat()
        rows.append({
            "name": entry.name,
            "index": index,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "sha256": _file_sha256(entry),
        })
    return rows


def restore_backup(
    project_path: str | os.PathLike[str],
    backup_name: str,
    expected_project_sha256: str,
) -> dict[str, Any]:
    """Replace the project with one of its backups; the current file is backed up first.

    ``backup_name`` must be a bare file name returned by ``list_backups``.
    ``expected_project_sha256`` is the hash the caller last saw; a mismatch means the
    project changed since then and nothing is touched.
    """
    project = Path(project_path).expanduser().resolve()
    if not project.is_file():
        raise BackupError("Project path must point to an existing file.", 404)
    if not re.fullmatch(r"[a-f0-9]{64}", expected_project_sha256 or ""):
        raise BackupError("expected_project_sha256 must be a 64-character lowercase hex SHA-256.")
    # Bare names only: no separators, no traversal, and it must match this project's scheme.
    if (
        backup_name != Path(backup_name).name
        or "/" in backup_name
        or "\\" in backup_name
        or not _pattern(project).match(backup_name)
    ):
        raise BackupError("backup_name must be a backup file name for this project, as returned by list_backups.")
    backup = project.with_name(backup_name)
    if not backup.is_file() or backup.is_symlink():
        raise BackupError(f"Backup not found: {backup_name}", 404)
    return _swap_in(project, backup, expected_project_sha256)


def _swap_in(project: Path, backup: Path, expected_sha256: str) -> dict[str, Any]:
    if _file_sha256(project) != expected_sha256:
        raise BackupError("Project changed on disk since it was loaded. Reload it before restoring.", 409)
    temp_path: Path | None = None
    try:
        # The temp file keeps the project's suffix so load_project() validates the right type.
        fd, temp_name = tempfile.mkstemp(prefix=f".{project.stem}.", suffix=project.suffix, dir=project.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        shutil.copyfile(backup, temp_path)
        try:
            # load_project() picks the file type from the extension, so it must see the
            # temp copy (project suffix), not the ".bak" name. This validates exactly
            # what will be swapped in.
            load_project(temp_path)
        except ProjectReadError as exc:
            raise BackupError(f"Backup is not a safe, readable project and was not restored: {exc}") from exc
        if _file_sha256(project) != expected_sha256:
            raise BackupError("Project changed while the restore was being prepared. Nothing was changed.", 409)
        safety = next_backup_path(project)
        shutil.copy2(project, safety)  # so the restore itself can be undone
        shutil.copystat(project, temp_path)
        os.replace(temp_path, project)
        temp_path = None
    except BackupError:
        raise
    except (OSError, ProjectReadError) as exc:
        raise BackupError(f"Could not safely restore the backup: {exc}") from exc
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return {
        "restored": True,
        "restored_from": backup.name,
        "safety_backup": safety.name,
        "project_sha256": _file_sha256(project),
        "note": "Backup restored. The previous project file was saved as the safety backup.",
    }
