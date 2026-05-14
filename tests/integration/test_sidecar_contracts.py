"""
Integration-style checks for path resolution, topic tree payload, and preview path rules.

Requires project dependencies (see pyproject.toml). Run: pytest tests/integration/
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from config import config
from modules.file_preview import FilePreviewer
from sidecar.paths import find_file_by_name_in_workspace, resolve_workspace_path
from utils.topic_assigner import parse_wiki_structure


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    (d / "Notes").mkdir()
    (d / "Abstract").mkdir()
    config.workspace_path = str(d)
    return d


class TestResolveWorkspacePath:
    def test_relative_path_inside_workspace(self, workspace: Path) -> None:
        rel = "Notes/hello.md"
        f = workspace / rel
        f.write_text("# x", encoding="utf-8")
        got = resolve_workspace_path(rel)
        assert got == str(f.resolve())

    def test_absolute_path_inside_workspace(self, workspace: Path) -> None:
        f = workspace / "Notes" / "a.md"
        f.write_text("y", encoding="utf-8")
        got = resolve_workspace_path(str(f))
        assert got == str(f.resolve())

    def test_rejects_escape_outside_workspace(self, workspace: Path) -> None:
        outside = workspace.parent / "evil.md"
        outside.write_text("z", encoding="utf-8")
        assert resolve_workspace_path(str(outside)) is None

    def test_returns_none_when_workspace_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "workspace_path", "", raising=False)
        assert resolve_workspace_path("Notes/x.md") is None


class TestFindFileByName:
    def test_finds_first_match_in_workspace(self, workspace: Path) -> None:
        (workspace / "Abstract" / "dup.md").write_text("1", encoding="utf-8")
        got = find_file_by_name_in_workspace("Abstract/dup.md")
        assert got is not None
        assert got.endswith("dup.md")


class TestGetTopicTreeContract:
    """Shape of `get_topic_tree` RPC (TopicsHandler._get_topic_tree → parse_wiki_structure)."""

    def test_returns_topics_and_pending_lists(self, workspace: Path) -> None:
        tree = parse_wiki_structure(Path(config.workspace_path))
        assert set(tree) == {"topics", "pending"}
        assert isinstance(tree["topics"], list)
        assert isinstance(tree["pending"], list)

    def test_pending_json_roundtrip(self, workspace: Path) -> None:
        pending_path = workspace / ".pending_topics.json"
        sample = [{"file": "Notes/a.md", "title": "A", "candidates": ["T1"]}]
        pending_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        tree = parse_wiki_structure(Path(config.workspace_path))
        assert len(tree.get("pending", [])) == 1


class TestPreviewPathContract:
    """
    Preview pipeline: resolve → absolute path → FilePreviewer.get_preview_data.
    Relative paths must still work when workspace_path is set on FilePreviewer.
    """

    def test_absolute_resolved_path_matches_existing_file(self, workspace: Path) -> None:
        rel = "Notes/preview.md"
        f = workspace / rel
        f.write_text("# Title\n\nbody", encoding="utf-8")
        abs_path = resolve_workspace_path(rel)
        assert abs_path is not None
        prev = FilePreviewer(str(workspace))
        data = prev.get_preview_data(abs_path)
        assert data.get("success") is True
        assert data.get("type") == "markdown"
        assert "Title" in (data.get("content") or "")

    def test_relative_path_joined_with_workspace(self, workspace: Path) -> None:
        rel = "Notes/rel.md"
        (workspace / rel).write_text("# R", encoding="utf-8")
        prev = FilePreviewer(str(workspace))
        data = prev.get_preview_data(rel)
        assert data.get("success") is True

    def test_missing_file_returns_error_not_success(self, workspace: Path) -> None:
        prev = FilePreviewer(str(workspace))
        data = prev.get_preview_data("Notes/nope.md")
        assert data.get("success") is False
        assert data.get("error") == "文件不存在"