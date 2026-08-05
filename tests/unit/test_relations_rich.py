"""Tests for tier-3: cross-block co-occurrence relations and topic-page summaries."""

from __future__ import annotations

from pathlib import Path

import pytest
from sidecar.semantic.ids import stable_id
from sidecar.semantic.store import SemanticStore
from sidecar.semantic.wiki import build_topic_wiki_page

from config import config


@pytest.fixture
def relation_store(tmp_path: Path):
    store = SemanticStore(tmp_path / "ws")
    store.initialize()
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-1', 'Notes/AI/RAG.md', 'h', 'RAG', 'AI > RAG', '2026-07-17T10:00:00Z')"""
        )
        for i in (1, 2):
            conn.execute(
                """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                      content, content_hash, start_line, end_line)
                   VALUES(?, 'doc-1', 'paragraph', '[]', ?, '内容', 'hash', 1, 1)""",
                (f"block-{i}", i),
            )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('e1', 'BERT', 'model', '', 0.9, 'active')"
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('e2', 'RoBERTa', 'model', '', 0.8, 'active')"
        )
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('c1', '预训练', '', 0.9, 'active')"
        )
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('c2', '弱概念', '', 0.2, 'active')"
        )
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('c3', '同块概念', '', 0.7, 'active')"
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('e1', 'entity', 'block-1')")
        conn.execute("INSERT INTO semantic_mentions VALUES('e2', 'entity', 'block-1')")
        conn.execute("INSERT INTO semantic_mentions VALUES('e1', 'entity', 'block-2')")
        conn.execute("INSERT INTO semantic_mentions VALUES('c1', 'concept', 'block-1')")
        conn.execute("INSERT INTO semantic_mentions VALUES('c1', 'concept', 'block-2')")
        conn.execute("INSERT INTO semantic_mentions VALUES('c2', 'concept', 'block-1')")
        conn.execute("INSERT INTO semantic_mentions VALUES('c2', 'concept', 'block-2')")
        conn.execute("INSERT INTO semantic_mentions VALUES('c3', 'concept', 'block-1')")
        # 预先存在的自动块级边 e1→c1（将被跨块加权边替换）。
        conn.execute(
            """INSERT INTO relations(id, source_id, relation_type, target_id, confidence, evidence_id, block_id)
               VALUES('block-rel-1', 'e1', 'RELATED_TO', 'c1', 0.9, NULL, 'block-1')"""
        )
    store.rebuild_document_relations({"doc-1"})
    return store


def _relations(store: SemanticStore) -> list[tuple[str, str, float, object]]:
    with store.connect() as conn:
        return [
            (row["source_id"], row["target_id"], row["confidence"], row["block_id"])
            for row in conn.execute("SELECT * FROM relations")
        ]


def test_same_block_entity_entity_relation(relation_store: SemanticStore) -> None:
    # e1 与 e2 仅同块共现 → 块级边，置信度 = min(0.9, 0.8)。
    expected_id = stable_id("relation", "block-1", "e1", "RELATED_TO", "e2")
    with relation_store.connect() as conn:
        row = conn.execute("SELECT * FROM relations WHERE id = ?", (expected_id,)).fetchone()
    assert row is not None
    assert row["source_id"] == "e1"
    assert row["target_id"] == "e2"
    assert row["confidence"] == pytest.approx(0.8)
    assert row["block_id"] == "block-1"


def test_same_block_concept_concept_relation(relation_store: SemanticStore) -> None:
    # c1 与 c3 仅同块共现（概念↔概念，原实现不建此类边）。
    expected_id = stable_id("relation", "block-1", "c1", "RELATED_TO", "c3")
    with relation_store.connect() as conn:
        row = conn.execute("SELECT * FROM relations WHERE id = ?", (expected_id,)).fetchone()
    assert row is not None
    assert row["source_id"] == "c1"
    assert row["target_id"] == "c3"
    assert row["confidence"] == pytest.approx(0.7)


def test_cross_block_frequency_weighted_relation(relation_store: SemanticStore) -> None:
    # e1 与 c1 在 block-1、block-2 共同出现 → 跨块加权边替换原块级边。
    # 加权 = min(0.9, 0.9) + 0.08 * 2 = 0.99。
    pairs = [(s, t) for s, t, _c, _b in _relations(relation_store)]
    assert ("c1", "e1") in pairs or ("e1", "c1") in pairs
    with relation_store.connect() as conn:
        row = conn.execute(
            "SELECT * FROM relations WHERE ((source_id='e1' AND target_id='c1') OR (source_id='c1' AND target_id='e1'))"
            " AND block_id IS NULL"
        ).fetchone()
    assert row is not None, "应存在跨块共现边"
    assert row["confidence"] == pytest.approx(0.99)
    # 原自动块级边被替换删除。
    with relation_store.connect() as conn:
        legacy = conn.execute("SELECT id FROM relations WHERE id = 'block-rel-1'").fetchone()
    assert legacy is None


def test_weak_cross_block_pair_skipped(relation_store: SemanticStore) -> None:
    # c2 与 e1/c1 跨块共现但 base=0.2 → weighted=0.36 < 0.4 → 不建跨块边。
    # （同块边维持现状无门禁，故只断言跨块边。）
    cross_block_pairs = {(s, t) for s, t, _c, b in _relations(relation_store) if b is None}
    assert not any(("c2" in pair) for pair in cross_block_pairs)


def test_entity_concept_same_block_not_duplicated(relation_store: SemanticStore) -> None:
    # e2 与 c1 仅同块共现（entity↔concept）：不重复建边（原块级逻辑负责），
    # 但 pre-existing 块级边被跨块替换后，e2↔c1 无边。
    pairs = {(s, t) for s, t, _c, _b in _relations(relation_store)}
    assert not any(("e2" in pair and "c1" in pair) for pair in pairs)


@pytest.fixture
def topic_store(tmp_path: Path):
    previous = config.workspace_path
    workspace = tmp_path / "workspace"
    (workspace / "Notes" / "AI").mkdir(parents=True)
    config.workspace_path = str(workspace)
    store = SemanticStore(workspace)
    store.initialize()
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-1', 'Notes/AI/RAG.md', 'h', 'RAG', 'AI > RAG', '2026-07-17T10:00:00Z')"""
        )
        for i in (1, 2, 3):
            conn.execute(
                """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                      content, content_hash, start_line, end_line)
                   VALUES(?, 'doc-1', 'paragraph', '[]', ?, '内容', 'hash', 1, 1)""",
                (f"block-{i}", i),
            )
        # 高频概念（3 次提及）：应出现在摘要。
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('c1', '混合检索', '同时使用向量与关键词', 0.9, 'active')"
        )
        # 低频低置信度实体：不应出现在摘要。
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('e1', '冷门实体', 'tool', '偶尔出现', 0.4, 'active')"
        )
        for i in (1, 2, 3):
            conn.execute("INSERT INTO semantic_mentions VALUES('c1', 'concept', ?)", (f"block-{i}",))
        conn.execute("INSERT INTO semantic_mentions VALUES('e1', 'entity', 'block-1')")
    yield store
    config.workspace_path = previous


def test_topic_page_empty_group_renders_object_summary(topic_store: SemanticStore) -> None:
    page = build_topic_wiki_page(topic_store, "AI")
    content = page["content"]
    assert "高频对象" in content
    assert "混合检索" in content
    assert "同时使用向量与关键词" in content
    assert "提及 3 次" in content
    # 低频低置信度对象被降级过滤。
    assert "冷门实体" not in content


def test_topic_page_with_claims_skips_object_summary(topic_store: SemanticStore) -> None:
    with topic_store.connect() as conn:
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
               VALUES('claim-1', '混合检索优于纯向量检索。', '', 'conclusion', 0.9, 'active')"""
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash)
               VALUES('evidence-1', 'claim-1', 'block-1', 'q')"""
        )
    page = build_topic_wiki_page(topic_store, "AI")
    assert "高频对象" not in page["content"]
    assert "混合检索优于纯向量检索。" in page["content"]
