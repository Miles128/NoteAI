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
from sidecar.pending_topics import load_pending_topics
from utils.topic_assigner import parse_wiki_structure


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    (d / "Notes").mkdir()
    (d / "wiki").mkdir(parents=True, exist_ok=True)
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
        (workspace / "wiki" / "dup.md").write_text("1", encoding="utf-8")
        got = find_file_by_name_in_workspace("wiki/dup.md")
        assert got is not None
        assert got.endswith("dup.md")


class TestParseWikiStructure:
    """parse_wiki_structure() parses WIKI.md into a list of topic dicts."""

    def test_returns_topic_list(self, workspace: Path) -> None:
        wiki_dir = workspace / "wiki"
        wiki_dir.mkdir(exist_ok=True)
        wiki = wiki_dir / "WIKI.md"
        wiki.write_text(
            "## AI 产品经理之路\n\n"
            "1. **产品思维**\n"
            "2. **需求分析**\n\n"
            "### Agent 架构\n\n"
            "1. **Agent 设计**\n",
            encoding="utf-8",
        )
        topics = parse_wiki_structure()
        assert isinstance(topics, list)
        assert len(topics) >= 2
        for t in topics:
            assert "name" in t
            assert "label" in t
            assert "files" in t
            assert isinstance(t["files"], list)

    def test_empty_when_no_wiki(self, workspace: Path) -> None:
        topics = parse_wiki_structure()
        assert topics == []


class TestPendingTopics:
    """load_pending_topics() reads .pending_topics.json from workspace."""

    def test_pending_json_roundtrip(self, workspace: Path) -> None:
        pending_path = workspace / ".pending_topics.json"
        sample = [{"file": "Notes/a.md", "title": "A", "candidates": ["T1"]}]
        pending_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
        pending = load_pending_topics()
        assert len(pending) == 1
        assert pending[0]["file"] == "Notes/a.md"

    def test_empty_when_no_file(self, workspace: Path) -> None:
        pending = load_pending_topics()
        assert pending == []


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