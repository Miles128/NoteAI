"""Tests for object-layer (entity/concept) retrieval injected into RAG chat."""

from __future__ import annotations

from pathlib import Path

import pytest
from sidecar.rag.object_context import retrieve_object_context
from sidecar.semantic.store import SemanticStore


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    store = SemanticStore(ws)
    store.initialize()
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-1', 'Notes/RAG.md', 'hash', 'RAG', 'RAG > 检索', '2026-08-01T00:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-2', 'Notes/LLM.md', 'hash2', 'LLM', 'LLM > 上下文', '2026-08-01T00:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-1', 'doc-1', 'paragraph', '["结论"]', 0, '内容。', 'block-hash', 1, 2)"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-2', 'doc-2', 'paragraph', '[]', 0, '内容。', 'block-hash-2', 1, 2)"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-3', 'doc-1', 'paragraph', '[]', 0, '内容。', 'block-hash-3', 1, 2)"""
        )
        # 高频概念：mention 2 次，高置信度 → 正常注入。
        conn.execute(
            """INSERT INTO concepts(id, canonical_name, description, confidence, status)
               VALUES('concept-1', '混合检索', '同时使用稠密向量与稀疏关键词的检索方法', 0.9, 'active')"""
        )
        # 高频实体：mention 2 次，高置信度 → 正常注入。
        conn.execute(
            """INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)
               VALUES('entity-1', 'BERT', 'model', '预训练语言模型', 0.85, 'active')"""
        )
        # 低频低置信度概念：mention 1 次 → 触发降级，不注入。
        conn.execute(
            """INSERT INTO concepts(id, canonical_name, description, confidence, status)
               VALUES('concept-2', '冷门术语', '很少出现的概念', 0.4, 'active')"""
        )
        conn.execute(
            """INSERT INTO semantic_mentions(object_id, object_kind, block_id)
               VALUES('concept-1', 'concept', 'block-1'),
                      ('concept-1', 'concept', 'block-2'),
                      ('entity-1', 'entity', 'block-1'),
                      ('entity-1', 'entity', 'block-3'),
                      ('concept-2', 'concept', 'block-2')"""
        )
    return ws


def test_no_semantic_db_returns_empty(tmp_path: Path) -> None:
    assert retrieve_object_context(tmp_path / "empty-workspace", "混合检索怎么样？") == []


def test_missing_question_or_workspace_returns_empty(workspace: Path) -> None:
    assert retrieve_object_context(workspace, "") == []
    assert retrieve_object_context("", "混合检索怎么样？") == []


def test_name_substring_hit(workspace: Path) -> None:
    items = retrieve_object_context(workspace, "混合检索相比纯向量检索优势在哪？")
    assert items, "问题包含概念名时应命中"
    entry = items[0]
    assert entry["source_type"] == "object"
    assert entry["object_id"] == "concept-1"
    assert entry["object_kind"] == "concept"
    assert "混合检索" in entry["content"]
    assert "稠密向量" in entry["content"]
    assert "知识库对象·概念" in entry["source_label"]
    assert entry["score"] == 1.0


def test_entity_hit_with_type_label(workspace: Path) -> None:
    items = retrieve_object_context(workspace, "BERT 的用途是什么？")
    assert items
    entry = items[0]
    assert entry["object_id"] == "entity-1"
    assert entry["object_kind"] == "entity"
    assert "知识库对象·实体（model）" in entry["source_label"]


def test_token_overlap_hit_without_exact_name(workspace: Path) -> None:
    # 名称「混合检索」不直接出现在问题里，但「检索」与名称/描述重叠。
    items = retrieve_object_context(workspace, "怎么用检索提升回答质量？")
    assert items
    assert items[0]["object_id"] == "concept-1"


def test_low_frequency_object_degraded(workspace: Path) -> None:
    items = retrieve_object_context(workspace, "冷门术语 是什么？")
    # 名称子串命中但低频低置信度 → 仍被降级过滤。
    assert items == []


def test_topic_filter(workspace: Path) -> None:
    items = retrieve_object_context(workspace, "BERT 是什么？", topics=["LLM > 上下文"])
    assert items == []
    items = retrieve_object_context(workspace, "BERT 是什么？", topics=["RAG > 检索"])
    assert items and items[0]["object_id"] == "entity-1"


def test_limit_respected(workspace: Path) -> None:
    items = retrieve_object_context(workspace, "检索 混合 向量 上下文", limit=1)
    assert len(items) == 1


def test_irrelevant_question_returns_empty(workspace: Path) -> None:
    assert retrieve_object_context(workspace, "今天天气怎么样") == []
