from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from sidecar import workspace_backup as wb

from config import config


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A workspace with content folders, derived indices and metadata files."""
    root = tmp_path / "workspace"
    (root / "Notes" / "AI").mkdir(parents=True)
    (root / "wiki" / "AI").mkdir(parents=True)
    (root / "Raw").mkdir(parents=True)
    (root / "RawArchive").mkdir(parents=True)
    # Derived / disposable content that backups must exclude.
    (root / ".rag").mkdir(parents=True)
    (root / "zvec" / "bm25").mkdir(parents=True)
    (root / ".semantic").mkdir(parents=True)
    (root / ".cache").mkdir(parents=True)
    (root / ".trash").mkdir(parents=True)
    (root / ".git").mkdir(parents=True)
    (root / ".rag" / "collection.bin").write_text("x", encoding="utf-8")
    (root / "zvec" / "bm25" / "index.bin").write_text("x", encoding="utf-8")
    (root / ".semantic" / "store.db").write_text("x", encoding="utf-8")
    (root / ".cache" / "tmp.bin").write_text("x", encoding="utf-8")
    (root / ".trash" / "old.bin").write_text("x", encoding="utf-8")
    (root / ".git" / "config").write_text("x", encoding="utf-8")
    (root / ".DS_Store").write_text("x", encoding="utf-8")
    # Real content.
    (root / "Notes" / "AI" / "RAG.md").write_text("# RAG 笔记\n\n正文内容。", encoding="utf-8")
    (root / "Notes" / "README.md").write_text("# 说明", encoding="utf-8")
    (root / "wiki" / "AI" / "RAG.md").write_text("# 编译产物", encoding="utf-8")
    (root / "Raw" / "source.pdf").write_text("pdf", encoding="utf-8")
    (root / "RawArchive" / "old.pdf").write_text("pdf", encoding="utf-8")
    (root / ".links.json").write_text('{"Notes/AI/RAG.md": []}', encoding="utf-8")
    (root / "tags.md").write_text("tags: RAG", encoding="utf-8")
    (root / "topics.md").write_text("topics: AI", encoding="utf-8")
    return root


@pytest.fixture
def configured(workspace: Path):
    previous = config.workspace_path
    config.workspace_path = str(workspace)
    yield workspace
    config.workspace_path = previous


def _names(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return set(zf.namelist())


def _manifest(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


def test_backup_contains_content_and_metadata_excludes_indices(configured: Path, tmp_path: Path) -> None:
    result = wb.backup_workspace(str(configured), target_dir=str(tmp_path))
    assert result["success"] is True
    zip_path = Path(result["backup_path"])
    assert zip_path.exists() and zip_path.suffix == ".zip"

    names = _names(zip_path)
    assert "manifest.json" in names
    assert "Notes/AI/RAG.md" in names
    assert "Notes/README.md" in names
    assert "wiki/AI/RAG.md" in names
    assert "Raw/source.pdf" in names
    assert "RawArchive/old.pdf" in names
    assert ".links.json" in names
    assert "tags.md" in names
    assert "topics.md" in names
    # Derived / disposable entries excluded.
    for excluded in (".rag/", "zvec/", ".semantic/", ".cache/", ".trash/", ".git/", ".DS_Store"):
        assert not any(n.startswith(excluded) for n in names), excluded

    manifest = _manifest(zip_path)
    assert manifest["app"] == "NoteAI"
    assert manifest["kind"] == "workspace-backup"
    assert manifest["file_count"] == len(names) - 1


def test_backup_without_workspace_fails(configured: Path) -> None:
    result = wb.backup_workspace("", target_dir=str(configured))
    assert result["success"] is False


def test_backup_missing_workspace_dir_fails(tmp_path: Path) -> None:
    result = wb.backup_workspace(str(tmp_path / "nope"), target_dir=str(tmp_path))
    assert result["success"] is False


def test_export_notes_keeps_only_notes_and_tags(configured: Path, tmp_path: Path) -> None:
    result = wb.export_notes(str(configured), target_dir=str(tmp_path))
    assert result["success"] is True
    names = _names(Path(result["backup_path"]))
    assert "Notes/AI/RAG.md" in names
    assert "tags.md" in names
    assert "manifest.json" in names
    for absent in ("wiki/AI/RAG.md", "Raw/source.pdf", "RawArchive/old.pdf", ".links.json", "topics.md"):
        assert absent not in names, absent


def test_restore_round_trip_moves_previous_content_to_trash(configured: Path, tmp_path: Path) -> None:
    # 1) Backup the populated workspace.
    backup = wb.backup_workspace(str(configured), target_dir=str(tmp_path))
    assert backup["success"] is True
    backup_path = backup["backup_path"]

    # 2) Mutate the workspace (delete wiki, alter a note, drop Raw).
    (configured / "wiki").rename(configured / "wiki-removed")
    (configured / "Notes" / "AI" / "RAG.md").write_text("# 已改写", encoding="utf-8")
    (configured / "Raw" / "source.pdf").unlink()

    # 3) Restore.
    result = wb.restore_workspace_backup(str(configured), backup_path)
    assert result["success"] is True
    assert result["restored_count"] > 0
    assert result["workspace_name"] == "workspace"

    # Content is back to its backed-up state.
    assert (configured / "Notes" / "AI" / "RAG.md").read_text(encoding="utf-8") == "# RAG 笔记\n\n正文内容。"
    assert (configured / "wiki" / "AI" / "RAG.md").is_file()
    assert (configured / "Raw" / "source.pdf").is_file()
    assert (configured / ".links.json").is_file()

    # Previous state was preserved under .trash instead of being lost.
    trash = sorted(configured.glob(".trash/restore-*"))
    assert trash
    assert (trash[0] / "Notes" / "AI" / "RAG.md").read_text(encoding="utf-8") == "# 已改写"


def test_restore_rejects_non_noteai_zip(configured: Path, tmp_path: Path) -> None:
    evil = tmp_path / "not-noteai.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app": "Other", "kind": "x"}))
        zf.writestr("Notes/a.md", "x")
    result = wb.restore_workspace_backup(str(configured), str(evil))
    assert result["success"] is False
    assert "类型不匹配" in result["message"]


def test_restore_rejects_zip_without_manifest(configured: Path, tmp_path: Path) -> None:
    evil = tmp_path / "no-manifest.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("Notes/a.md", "x")
    result = wb.restore_workspace_backup(str(configured), str(evil))
    assert result["success"] is False
    assert "manifest" in result["message"]


def test_restore_rejects_path_traversal_entries(configured: Path, tmp_path: Path) -> None:
    """zip-slip: entries escaping the workspace must fail the whole restore."""
    evil = tmp_path / "traversal.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app": "NoteAI", "kind": "workspace-backup"}))
        zf.writestr("../escape.md", "x")
    result = wb.restore_workspace_backup(str(configured), str(evil))
    assert result["success"] is False
    assert "非法路径" in result["message"]
    # Nothing outside the workspace was created, and the workspace itself stayed put.
    assert not (tmp_path.parent / "escape.md").exists()
    assert (tmp_path / "workspace").is_dir()


def test_restore_rejects_missing_backup_file(configured: Path) -> None:
    result = wb.restore_workspace_backup(str(configured), str(configured / "missing.zip"))
    assert result["success"] is False


def test_check_index_health_returns_all_layers(configured: Path) -> None:
    report = wb.check_index_health(str(configured))
    assert report["success"] is True
    for key in ("rag", "semantic", "links", "fulltext"):
        assert key in report
        assert "ok" in report[key]
        assert "detail" in report[key]
    assert report["fulltext"]["ok"] is True
    assert report["links"]["ok"] is True
    assert report["semantic"]["note_files"] == 2


def test_check_index_health_without_workspace_fails() -> None:
    report = wb.check_index_health("")
    assert report["success"] is False
