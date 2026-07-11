from pathlib import Path

import pytest

from config import config
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
