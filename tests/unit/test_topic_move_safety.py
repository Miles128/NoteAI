from pathlib import Path

import pytest

from config import config
from utils.topic_assigner import _apply_auto_topic
from utils.topic_file_ops import move_file_to_notes_topic_folder


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    (root / "Notes").mkdir(parents=True)
    config.workspace_path = str(root)
    return root


@pytest.mark.parametrize("topic", ["安全 > /tmp", "安全 > ..", "安全 > 子\\目录"])
def test_move_rejects_topic_path_components(workspace: Path, topic: str) -> None:
    note = workspace / "Notes" / "note.md"
    note.write_text("# note", encoding="utf-8")

    result = move_file_to_notes_topic_folder(str(note), topic)

    assert result["success"] is False
    assert note.is_file()


def test_move_reports_success_with_new_relative_path(workspace: Path) -> None:
    note = workspace / "Notes" / "note.md"
    note.write_text("# note", encoding="utf-8")

    result = move_file_to_notes_topic_folder(str(note), "技术 > Python")

    assert result["success"] is True
    assert result["new_path"] == "Notes/技术/Python/note.md"
    assert (workspace / result["new_path"]).is_file()


def test_auto_topic_reports_move_failure_instead_of_success(workspace: Path, monkeypatch) -> None:
    note = workspace / "Notes" / "note.md"
    note.write_text("# note", encoding="utf-8")
    monkeypatch.setattr(
        "utils.topic_assigner.move_file_to_notes_topic_folder",
        lambda *_args, **_kwargs: {"success": False, "message": "disk full"},
    )

    result = _apply_auto_topic(note, str(workspace), "技术 > Python", "note", None, False)

    assert result == {"status": "error", "message": "disk full", "format_optimized": False}


def test_auto_topic_returns_final_moved_path(workspace: Path) -> None:
    note = workspace / "Notes" / "note.md"
    note.write_text("# note", encoding="utf-8")

    result = _apply_auto_topic(note, str(workspace), "技术 > Python", "note", None, False)

    expected = workspace / "Notes" / "技术" / "Python" / "note.md"
    assert result["status"] == "auto_assigned"
    assert result["new_path"] == "Notes/技术/Python/note.md"
    assert result["file_path"] == str(expected)
    assert expected.is_file()
