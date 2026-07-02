from pathlib import Path

import pytest

from config import config
from sidecar.workspace_meta import (
    is_inbox_orphan_path,
    is_workspace_meta_path,
    merge_meta_docs_into_project_rules,
)
from utils.topic_assigner import auto_assign_topic_for_file, sync_all_folder_topics


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes" / "AI" / "二级").mkdir(parents=True)
    (d / "wiki").mkdir()
    (d / ".ai_memory").mkdir()
    config.workspace_path = str(d)
    return d


def test_is_workspace_meta_path() -> None:
    assert is_workspace_meta_path("AGENTS.md")
    assert is_workspace_meta_path("Notes/CLAUDE.md")
    assert not is_workspace_meta_path("Notes/readme.md")


def test_merge_meta_docs_into_project_rules(workspace: Path) -> None:
    (workspace / "AGENTS.md").write_text("# Agents\n\nRule A\n", encoding="utf-8")
    (workspace / "Notes" / "CLAUDE.md").write_text("# Claude\n\nRule B\n", encoding="utf-8")
    result = merge_meta_docs_into_project_rules(str(workspace))
    assert result["merged"] == 2
    assert not (workspace / "AGENTS.md").exists()
    assert not (workspace / "Notes" / "CLAUDE.md").exists()
    rules = (workspace / ".ai_memory" / "project_rules.md").read_text(encoding="utf-8")
    assert "Rule A" in rules
    assert "Rule B" in rules


def test_is_inbox_orphan_path(workspace: Path) -> None:
    assert is_inbox_orphan_path(workspace / "orphan.md", str(workspace))
    assert is_inbox_orphan_path(workspace / "Notes" / "loose.md", str(workspace))
    assert not is_inbox_orphan_path(workspace / "Notes" / "AI" / "note.md", str(workspace))
    assert not is_inbox_orphan_path(workspace / "AGENTS.md", str(workspace))


def test_sync_folder_topics_for_subfolder_file(workspace: Path) -> None:
    note = workspace / "Notes" / "AI" / "二级" / "note.md"
    note.write_text("# hello\n", encoding="utf-8")
    updated = sync_all_folder_topics(str(workspace))
    assert updated == 1
    text = note.read_text(encoding="utf-8")
    assert "topic: AI > 二级" in text


def test_auto_assign_skips_non_inbox_without_llm(workspace: Path) -> None:
    note = workspace / "Notes" / "AI" / "note.md"
    note.write_text("# hello\n", encoding="utf-8")
    result = auto_assign_topic_for_file(str(note), use_llm=False)
    assert result and result.get("status") == "auto_assigned"
    assert result.get("topic") == "AI"
