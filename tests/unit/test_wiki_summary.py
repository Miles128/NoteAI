from pathlib import Path

import pytest

from config import config
from utils.wiki_sync import sync_wiki_with_files


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    notes = d / "Notes" / "AI" / "基础"
    notes.mkdir(parents=True)
    (d / "wiki").mkdir()
    (notes / "笔记.md").write_text("# 标题\n\n这是摘要第一句。\n", encoding="utf-8")
    (d / "schema.md").write_text(
        "<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    config.workspace_path = str(d)
    return d


def test_sync_wiki_includes_topic_summary(workspace: Path) -> None:
    result = sync_wiki_with_files()
    assert result["success"] is True
    wiki = (workspace / "wiki" / "WIKI.md").read_text(encoding="utf-8")
    assert "> " in wiki
    assert "摘要" in wiki or "标题" in wiki


def test_sync_wiki_is_noop_when_database_is_accurate(workspace: Path) -> None:
    first = sync_wiki_with_files()
    wiki_path = workspace / "wiki" / "WIKI.md"
    first_mtime = wiki_path.stat().st_mtime_ns

    second = sync_wiki_with_files()

    assert first["changed"] is True
    assert second["changed"] is False
    assert wiki_path.stat().st_mtime_ns == first_mtime


def test_wiki_contains_managed_tags_and_no_tags_file(workspace: Path) -> None:
    note = workspace / "Notes" / "AI" / "基础" / "标签笔记.md"
    note.write_text("---\ntags: [RAG, 检索]\n---\n正文\n", encoding="utf-8")
    legacy = workspace / "wiki" / "tags.md"
    legacy.write_text("# Tags\n", encoding="utf-8")

    result = sync_wiki_with_files()
    wiki = (workspace / "wiki" / "WIKI.md").read_text(encoding="utf-8")

    assert result["tags"] == 2
    assert "<!-- NOTEAI_TAGS_START -->" in wiki
    assert "- **RAG**: `Notes/AI/基础/标签笔记.md`" in wiki
    assert "- **检索**: `Notes/AI/基础/标签笔记.md`" in wiki
    assert not legacy.exists()


def test_wiki_tag_headings_are_not_topics(workspace: Path) -> None:
    from utils.wiki_manager import parse_wiki_headings, parse_wiki_structure

    note = workspace / "Notes" / "AI" / "基础" / "标签笔记.md"
    note.write_text("---\ntags: [RAG]\n---\n正文\n", encoding="utf-8")
    sync_wiki_with_files()

    assert all(item["label"] != "标签索引" for item in parse_wiki_headings())
    assert all(item["label"] != "标签索引" for item in parse_wiki_structure())
