"""Tests for merged top-level topic wiki pages and WIKI.md bookshelf linking."""

from __future__ import annotations

from pathlib import Path

import pytest
from sidecar.semantic.store import SemanticStore
from sidecar.semantic.wiki import build_topic_wiki_page, materialize_topic_wiki_page, top_level_topic
from sidecar.wiki_utils import sync_semantic_links

from config import config


@pytest.fixture
def merged_store(tmp_path: Path):
    previous = config.workspace_path
    workspace = tmp_path / "workspace"
    (workspace / "Notes" / "AI").mkdir(parents=True)
    config.workspace_path = str(workspace)
    store = SemanticStore(workspace)
    store.initialize()
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-1', 'Notes/AI/RAG.md', 'h1', 'RAG', 'AI > RAG', '2026-07-17T10:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-2', 'Notes/AI/RAG/细节.md', 'h2', '细节', 'AI > RAG > 细节',
                      '2026-07-17T10:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-1', 'doc-1', 'paragraph', '["检索"]', 0,
                      '混合检索结合向量与关键词。', 'bh1', 8, 8)"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-2', 'doc-2', 'paragraph', '["细节"]', 0,
                      'RAG 细节说明。', 'bh2', 1, 1)"""
        )
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
               VALUES('claim-1', '混合检索结合向量与关键词。', 'RAG', 'conclusion', 0.92, 'active')"""
        )
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
               VALUES('claim-2', '细节决定成败。', '细节', 'conclusion', 0.8, 'active')"""
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash)
               VALUES('evidence-1', 'claim-1', 'block-1', 'q1')"""
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash)
               VALUES('evidence-2', 'claim-2', 'block-2', 'q2')"""
        )
    yield store
    config.workspace_path = previous


def test_top_level_topic_normalization() -> None:
    assert top_level_topic("AI") == "AI"
    assert top_level_topic("AI > RAG") == "AI"
    assert top_level_topic("AI > RAG > 细节") == "AI"


def test_top_level_page_merges_descendant_sections(merged_store: SemanticStore) -> None:
    target = materialize_topic_wiki_page(merged_store, "AI")
    content = target.read_text(encoding="utf-8")

    assert target.name == "AI_语义.md"
    assert target.parent.name == "semantic"
    assert content.startswith("---")
    assert "# AI" in content
    assert "## RAG" in content
    assert "### 细节" in content
    assert "混合检索结合向量与关键词。" in content
    assert "细节决定成败。" in content


def test_materialize_from_subtopic_writes_merged_top_level(merged_store: SemanticStore) -> None:
    target = materialize_topic_wiki_page(merged_store, "AI > RAG")
    content = target.read_text(encoding="utf-8")

    assert target.name == "AI_语义.md"
    assert "## RAG" in content
    assert "### 细节" in content


def test_subtopic_preview_returns_own_section(merged_store: SemanticStore) -> None:
    page = build_topic_wiki_page(merged_store, "AI > RAG")

    assert page["input_hash"] is None
    assert page["target"].name == "AI_语义.md"
    assert "# RAG" in page["content"]
    assert "> 主题：AI > RAG" in page["content"]
    assert "## 细节" in page["content"]
    assert "# AI" not in page["content"]


def test_subtopic_preview_excludes_sibling_claims(merged_store: SemanticStore) -> None:
    with merged_store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-3', 'Notes/AI/其他.md', 'h3', '其他', 'AI > 其他',
                      '2026-07-17T10:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-3', 'doc-3', 'paragraph', '["其他"]', 0,
                      '其他内容。', 'bh3', 1, 1)"""
        )
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
               VALUES('claim-3', '无关兄弟命题。', '其他', 'conclusion', 0.7, 'active')"""
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash)
               VALUES('evidence-3', 'claim-3', 'block-3', 'q3')"""
        )

    page = build_topic_wiki_page(merged_store, "AI > RAG")

    assert "无关兄弟命题。" not in page["content"]
    assert "混合检索结合向量与关键词。" in page["content"]


def _seed_wiki(workspace: Path) -> None:
    wiki = workspace / "wiki"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "WIKI.md").write_text(
        "# WIKI\n\n主题数量: 1\n\n## 目录\n\n## AI\n> 综述内容\n1. **RAG**\n\n## 标签索引\n\n- **标签**: x\n",
        encoding="utf-8",
    )
    (wiki / "semantic").mkdir(parents=True, exist_ok=True)
    (wiki / "semantic" / "AI_语义.md").write_text("# AI\n", encoding="utf-8")


def test_sync_semantic_links_injects_and_is_idempotent(tmp_path: Path) -> None:
    previous = config.workspace_path
    workspace = tmp_path / "workspace"
    _seed_wiki(workspace)
    config.workspace_path = str(workspace)
    try:
        first = sync_semantic_links()
        second = sync_semantic_links()

        assert first["success"] is True
        assert first["injected"] == 1
        assert second["success"] is True
        assert second["injected"] == 0
        text = (workspace / "wiki" / "WIKI.md").read_text(encoding="utf-8")
        assert "- **语义知识卡**：[AI · 语义知识](semantic/AI_语义.md) <!-- NOTEAI_SEMANTIC_LINK -->" in text
        assert "## 标签索引" in text
        assert "语义知识卡" not in text.split("## 标签索引", 1)[1]
    finally:
        config.workspace_path = previous


def test_sync_semantic_links_skips_topics_without_cards(tmp_path: Path) -> None:
    previous = config.workspace_path
    workspace = tmp_path / "workspace"
    _seed_wiki(workspace)
    (workspace / "wiki" / "WIKI.md").write_text(
        "# WIKI\n\n## 目录\n\n## 无卡片主题\n> 综述\n1. **文件**\n",
        encoding="utf-8",
    )
    config.workspace_path = str(workspace)
    try:
        result = sync_semantic_links()

        assert result["success"] is True
        assert result["injected"] == 0
        text = (workspace / "wiki" / "WIKI.md").read_text(encoding="utf-8")
        assert "语义知识卡" not in text
    finally:
        config.workspace_path = previous
