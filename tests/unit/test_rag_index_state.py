from pathlib import Path

import pytest
from sidecar.rag.index_state import file_needs_index, load_state, mark_indexed, remove_indexed

from config import config


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
