import json
from pathlib import Path

import pytest
from sidecar.rag.index_state import file_needs_index, load_state, mark_indexed, remove_indexed

from config import config
from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir(parents=True, exist_ok=True)
    (d / "Notes").mkdir(parents=True, exist_ok=True)
    config.workspace_path = str(d)
    return d


def test_file_needs_index_when_new(workspace: Path) -> None:
    md = workspace / "Notes" / "a.md"
    md.write_text("# hi", encoding="utf-8")
    rel = "Notes/a.md"
    assert file_needs_index(rel, md.stat().st_mtime, str(workspace)) is True


def test_file_needs_index_after_marked(workspace: Path) -> None:
    md = workspace / "Notes" / "a.md"
    md.write_text("# hi", encoding="utf-8")
    rel = "Notes/a.md"
    mtime = md.stat().st_mtime
    mark_indexed(rel, mtime, str(workspace))
    assert file_needs_index(rel, mtime, str(workspace)) is False


def test_remove_indexed_for_deleted_file(workspace: Path) -> None:
    mark_indexed("Notes/deleted.md", 123.0, str(workspace))

    remove_indexed(["Notes/deleted.md"], str(workspace))

    assert load_state(str(workspace)) == {}


def test_missing_state_recovers_mtimes_from_manifest(workspace: Path) -> None:
    manifest_path = workspace / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER / "file_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps({"files": {"Notes/a.md": {"mtime": 123.5, "size": 10, "chunks": ["c1"]}}}),
        encoding="utf-8",
    )

    assert load_state(str(workspace)) == {"Notes/a.md": 123.5}
    assert file_needs_index("Notes/a.md", 123.5, str(workspace)) is False
