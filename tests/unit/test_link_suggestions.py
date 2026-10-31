"""Tests for link suggestions: same-topic rule, README exclusion, cross-ref discovery."""

from pathlib import Path

import pytest
from sidecar.schema_manager import SCHEMA_FILENAME

from config import config
from utils.link_indexer import (
    discover_cross_refs_for_file,
    load_links,
    suggest_links_for_file,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    notes = d / "Notes" / "AI" / "子题"
    notes.mkdir(parents=True)
    for i, title in enumerate(["源文章", "同主题A", "同主题B", "提及源", "标签友", "远房亲戚"]):
        p = notes / f"{title}.md"
        topic = "AI > 子题" if i < 3 else "AI > 其他"
        tags = "tags: [RAG, 测试]" if i == 4 else "tags: []"
        body = f"讨论 {title} 的内容。"
        if i == 3:
            body = "这里提到了源文章的核心观点。"
        p.write_text(f"---\ntopic: {topic}\n{tags}\n---\n\n# {title}\n\n{body}\n", encoding="utf-8")
    (d / "wiki").mkdir(parents=True, exist_ok=True)
    (d / SCHEMA_FILENAME).write_text(
        "# ok\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    config.workspace_path = str(d)
    return d


def test_suggest_links_same_topic(workspace: Path) -> None:
    a = workspace / "Notes" / "AI" / "a.md"
    b = workspace / "Notes" / "AI" / "b.md"
    a.write_text("---\ntopic: AI > 测试\n---\n\n内容\n", encoding="utf-8")
    b.write_text("---\ntopic: AI > 测试\n---\n\n其他\n", encoding="utf-8")
    result = suggest_links_for_file(str(a.relative_to(workspace)))
    assert result["success"] is True
    # 同主题不连双向链接：仅同属一个主题目录并不是实质关联，直接跳过
    assert result["added"] == 0
    links = load_links().get("links", [])
    # 不应生成任何链接
    assert not any(l.get("from") == str(a.relative_to(workspace)) for l in links)


def test_suggest_links_ignores_readme(workspace: Path) -> None:
    readme = workspace / "Notes" / "AI" / "README.md"
    note = workspace / "Notes" / "AI" / "note.md"
    readme.write_text("---\ntopic: AI > 测试\n---\n\n目录说明\n", encoding="utf-8")
    note.write_text("---\ntopic: AI > 测试\n---\n\n其他\n", encoding="utf-8")

    result = suggest_links_for_file(str(note.relative_to(workspace)))
    assert result["success"] is True
    links = load_links().get("links", [])
    assert not any("README.md" in (l.get("from", "") + l.get("to", "")) for l in links)

    readme_result = suggest_links_for_file(str(readme.relative_to(workspace)))
    assert readme_result["success"] is True
    assert readme_result["added"] == 0


def test_discover_cross_refs_finds_related(workspace: Path) -> None:
    rel = "Notes/AI/子题/源文章.md"
    result = discover_cross_refs_for_file(rel, max_links=8, use_llm=False)
    assert result["success"] is True
    assert result["added"] >= 1
    links = load_links().get("links", [])
    outgoing = [l for l in links if l.get("from") == rel]
    assert len(outgoing) >= 1
    # 严格判断：启发式/LLM 候选一律 pending，等待人工确认
    assert {l.get("status") for l in outgoing} == {"pending"}


def test_discover_cross_refs_ignores_readme_notes(workspace: Path) -> None:
    readme_rel = "Notes/AI/子题/README.md"
    (workspace / readme_rel).write_text(
        "---\ntopic: AI > 子题\ntags: [RAG]\n---\n\n# README\n\n目录说明，不是知识笔记。\n",
        encoding="utf-8",
    )

    readme_result = discover_cross_refs_for_file(readme_rel, max_links=8, use_llm=False)
    assert readme_result["success"] is True
    assert readme_result["added"] == 0

    rel = "Notes/AI/子题/源文章.md"
    result = discover_cross_refs_for_file(rel, max_links=8, use_llm=False)
    assert result["success"] is True
    links = load_links().get("links", [])
    assert not any("README.md" in (l.get("from", "") + l.get("to", "")) for l in links)
