import hashlib
import os
import zipfile
from pathlib import Path

import pytest

from construct2_ai_bridge.backups import BackupError, list_backups, next_backup_path, restore_backup

V1 = '<c2project><layouts><layout name="One" /></layouts></c2project>'
V2 = '<c2project><layouts><layout name="Two" /></layouts></c2project>'
V3 = '<c2project><layouts><layout name="Three" /></layouts></c2project>'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    path = tmp_path / "game.caproj"
    path.write_text(V3, encoding="utf-8")
    (tmp_path / "game.caproj.bak").write_text(V1, encoding="utf-8")
    (tmp_path / "game.caproj.bak.1").write_text(V2, encoding="utf-8")
    return path


def test_next_backup_path_follows_write_endpoint_scheme(tmp_path: Path) -> None:
    path = tmp_path / "game.caproj"
    path.write_text(V1, encoding="utf-8")
    assert next_backup_path(path).name == "game.caproj.bak"
    (tmp_path / "game.caproj.bak").write_text("x")
    assert next_backup_path(path).name == "game.caproj.bak.1"
    (tmp_path / "game.caproj.bak.1").write_text("x")
    assert next_backup_path(path).name == "game.caproj.bak.2"


def test_list_backups_oldest_first_and_ignores_lookalikes(project: Path) -> None:
    folder = project.parent
    (folder / "game.caproj.bak.10").write_text(V1, encoding="utf-8")
    (folder / "game.caproj.bak.txt").write_text("nope")
    (folder / "game.caproj.bak.1x").write_text("nope")
    (folder / "other.caproj.bak").write_text("nope")
    (folder / "xgame.caproj.bak").write_text("nope")
    (folder / "game.caproj.bak.2").mkdir()  # a directory with a matching name
    rows = list_backups(project)
    assert [r["name"] for r in rows] == ["game.caproj.bak", "game.caproj.bak.1", "game.caproj.bak.10"]
    assert [r["index"] for r in rows] == [0, 1, 10]
    assert rows[0]["sha256"] == hashlib.sha256(V1.encode()).hexdigest()
    assert rows[1]["size"] == len(V2.encode())


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unsupported")
def test_list_backups_skips_symlinks(project: Path, tmp_path: Path) -> None:
    target = tmp_path / "elsewhere.txt"
    target.write_text(V1)
    try:
        (tmp_path / "game.caproj.bak.5").symlink_to(target)
    except OSError:
        pytest.skip("cannot create symlinks here")
    assert "game.caproj.bak.5" not in [r["name"] for r in list_backups(project)]


def test_list_backups_empty_when_none(tmp_path: Path) -> None:
    path = tmp_path / "fresh.caproj"
    path.write_text(V1, encoding="utf-8")
    assert list_backups(path) == []


def test_restore_swaps_content_and_saves_safety_backup(project: Path) -> None:
    result = restore_backup(project, "game.caproj.bak", sha(project))
    assert project.read_text(encoding="utf-8") == V1
    assert result["restored"] and result["restored_from"] == "game.caproj.bak"
    assert result["safety_backup"] == "game.caproj.bak.2"  # next free name
    assert (project.parent / "game.caproj.bak.2").read_text(encoding="utf-8") == V3  # pre-restore content
    assert result["project_sha256"] == sha(project)
    assert (project.parent / "game.caproj.bak").read_text(encoding="utf-8") == V1  # source backup kept
    assert not [p for p in project.parent.iterdir() if p.name.startswith(".game.")]  # no temp leftovers


def test_restore_can_be_undone_via_safety_backup(project: Path) -> None:
    first = restore_backup(project, "game.caproj.bak", sha(project))
    restore_backup(project, first["safety_backup"], first["project_sha256"])
    assert project.read_text(encoding="utf-8") == V3


def test_restore_rejects_stale_project_hash(project: Path) -> None:
    stale = sha(project)
    project.write_text(V2 + "<!-- edited elsewhere -->", encoding="utf-8")
    before = project.read_bytes()
    with pytest.raises(BackupError) as exc:
        restore_backup(project, "game.caproj.bak", stale)
    assert exc.value.status_code == 409
    assert project.read_bytes() == before
    assert not (project.parent / "game.caproj.bak.2").exists()  # no safety backup either


@pytest.mark.parametrize("bad", [
    "../game.caproj.bak", "sub/game.caproj.bak", "sub\\game.caproj.bak", "/etc/passwd",
    "game.caproj", "other.caproj.bak", "game.caproj.bak.txt", "game.caproj.bak.", "", "..",
])
def test_restore_rejects_unsafe_or_foreign_names(project: Path, bad: str) -> None:
    before = project.read_bytes()
    with pytest.raises(BackupError):
        restore_backup(project, bad, sha(project))
    assert project.read_bytes() == before


def test_restore_rejects_bad_hash_format_and_missing_things(project: Path, tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="64-character"):
        restore_backup(project, "game.caproj.bak", "abc")
    with pytest.raises(BackupError) as missing_backup:
        restore_backup(project, "game.caproj.bak.9", sha(project))
    assert missing_backup.value.status_code == 404
    with pytest.raises(BackupError) as missing_project:
        restore_backup(tmp_path / "nope.caproj", "nope.caproj.bak", "0" * 64)
    assert missing_project.value.status_code == 404


def test_restore_refuses_corrupt_or_unsafe_backups(project: Path) -> None:
    folder = project.parent
    (folder / "game.caproj.bak").write_text("<c2project><layout>", encoding="utf-8")  # malformed
    (folder / "game.caproj.bak.1").write_text('<!DOCTYPE x [<!ENTITY y "z">]><x>&y;</x>', encoding="utf-8")
    before = project.read_bytes()
    for name in ("game.caproj.bak", "game.caproj.bak.1"):
        with pytest.raises(BackupError, match="not a safe, readable project"):
            restore_backup(project, name, sha(project))
    assert project.read_bytes() == before
    assert not (folder / "game.caproj.bak.2").exists()


def test_restore_works_for_capx_archives(tmp_path: Path) -> None:
    def make(path: Path, layout: str) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("project.xml", f'<c2project><layouts><layout name="{layout}" /></layouts></c2project>')

    project = tmp_path / "game.capx"
    make(project, "New")
    make(tmp_path / "game.capx.bak", "Old")
    restore_backup(project, "game.capx.bak", sha(project))
    with zipfile.ZipFile(project) as archive:
        assert b'name="Old"' in archive.read("project.xml")
    assert (tmp_path / "game.capx.bak.1").exists()  # safety backup of the "New" archive
    with zipfile.ZipFile(tmp_path / "game.capx.bak.1") as archive:
        assert b'name="New"' in archive.read("project.xml")
