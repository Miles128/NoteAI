"""Tests for deterministic structured claim-conflict detection (prototype)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sidecar.semantic.conflict_detector import (
    detect_claim_conflicts,
    extract_polarities,
    persist_claim_conflicts,
    scan_and_persist,
)
from sidecar.semantic.store import SemanticStore


@pytest.fixture
def store(tmp_path: Path) -> SemanticStore:
    semantic_store = SemanticStore(tmp_path / "workspace")
    semantic_store.initialize()
    with semantic_store.connect() as conn:
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
    yield semantic_store


def _add_claim(
    store: SemanticStore,
    claim_id: str,
    statement: str,
    *,
    topic: str = "RAG > 检索",
    claim_type: str = "conclusion",
    scope: str = "",
    block_id: str = "block-1",
) -> None:
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status, user_edited)
               VALUES(?, ?, ?, ?, 0.9, 'active', 0)""",
            (claim_id, statement, scope, claim_type),
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash, status)
               VALUES(?, ?, ?, 'qh', 'active')""",
            (f"evidence-{claim_id}", claim_id, block_id),
        )


class TestExtractPolarities:
    def test_comparison_pair(self) -> None:
        found = extract_polarities("混合检索优于纯向量检索")
        assert len(found) == 1
        item = found[0]
        assert item.kind == "comparison"
        assert item.subject == "混合检索"
        assert item.target == "纯向量检索"
        assert item.direction == 1

    def test_reversed_comparison_collapses_to_same_key(self) -> None:
        # 「Y 劣于 X」在方向上等价于「X 优于 Y」，必须归一化到同一冲突键。
        left = extract_polarities("纯向量检索劣于混合检索")[0]
        right = extract_polarities("混合检索优于纯向量检索")[0]
        assert left.subject == right.subject
        assert left.target == right.target
        assert left.direction == right.direction

    def test_negated_direction(self) -> None:
        found = extract_polarities("混合检索劣于纯向量检索")
        assert found[0].direction == -1

    def test_change_verb(self) -> None:
        found = extract_polarities("该方法提升了召回率")
        assert found[0].kind == "change"
        assert found[0].direction == 1
        assert extract_polarities("该方法降低了召回率")[0].direction == -1

    def test_attribute_verb(self) -> None:
        assert extract_polarities("该方案有效")[0].kind == "attribute"
        assert extract_polarities("该方案无效")[0].direction == -1

    def test_plain_facts_extract_nothing(self) -> None:
        for statement in ("该工具支持 75 种模型", "Python 3.10 发布于 2021 年", "运行 uv sync 安装依赖"):
            assert extract_polarities(statement) == []


class TestDetectConflicts:
    def test_comparison_conflict_same_topic(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "混合检索优于纯向量检索", topic="RAG > 检索")
        _add_claim(store, "claim-b", "纯向量检索优于混合检索", topic="RAG > 检索")
        candidates = detect_claim_conflicts(store)
        assert len(candidates) == 1
        assert {candidates[0]["claim_a_id"], candidates[0]["claim_b_id"]} == {"claim-a", "claim-b"}
        assert candidates[0]["rule"] == "comparison"

    def test_reversed_phrasing_still_conflicts(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "混合检索优于纯向量检索", topic="RAG > 检索")
        _add_claim(store, "claim-b", "混合检索劣于纯向量检索", topic="RAG > 检索")
        assert len(detect_claim_conflicts(store)) == 1

    def test_change_conflict(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "该方法提升了召回率", topic="RAG > 检索")
        _add_claim(store, "claim-b", "该方法降低了召回率", topic="RAG > 检索")
        candidates = detect_claim_conflicts(store)
        assert len(candidates) == 1
        assert candidates[0]["kind"] == "change"

    def test_attribute_conflict(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "该方案有效", topic="RAG > 检索")
        _add_claim(store, "claim-b", "该方案无效", topic="RAG > 检索")
        assert len(detect_claim_conflicts(store)) == 1

    def test_same_direction_is_not_a_conflict(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "混合检索优于纯向量检索", topic="RAG > 检索")
        _add_claim(store, "claim-b", "混合检索优于BM25", topic="RAG > 检索")
        assert detect_claim_conflicts(store) == []

    def test_different_topic_without_scope_is_not_a_conflict(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "混合检索优于纯向量检索", topic="RAG > 检索")
        _add_claim(store, "claim-b", "纯向量检索优于混合检索", topic="LLM > 上下文", block_id="block-2")
        assert detect_claim_conflicts(store) == []

    def test_same_scope_bridges_different_topics(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "混合检索优于纯向量检索", topic="RAG > 检索", scope="中文语料")
        _add_claim(store, "claim-b", "纯向量检索优于混合检索", topic="LLM > 上下文", block_id="block-2", scope="中文语料")
        assert len(detect_claim_conflicts(store)) == 1

    def test_hypotheses_do_not_participate(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "混合检索优于纯向量检索", topic="RAG > 检索")
        _add_claim(store, "claim-b", "纯向量检索优于混合检索", topic="RAG > 检索", claim_type="hypothesis")
        assert detect_claim_conflicts(store) == []

    def test_deleted_claims_do_not_participate(self, store: SemanticStore) -> None:
        _add_claim(store, "claim-a", "混合检索优于纯向量检索", topic="RAG > 检索")
        _add_claim(store, "claim-b", "纯向量检索优于混合检索", topic="RAG > 检索")
        with store.connect() as conn:
            conn.execute("UPDATE claims SET status = 'deleted' WHERE id = 'claim-b'")
        assert detect_claim_conflicts(store) == []


class TestPersist:
    def _seed_conflict(self, store: SemanticStore) -> list[dict]:
        _add_claim(store, "claim-a", "混合检索优于纯向量检索", topic="RAG > 检索")
        _add_claim(store, "claim-b", "纯向量检索优于混合检索", topic="RAG > 检索")
        return detect_claim_conflicts(store)

    def test_persist_is_idempotent_and_reviewed_status_survives(self, store: SemanticStore) -> None:
        candidates = self._seed_conflict(store)
        result = persist_claim_conflicts(store, candidates)
        assert result["success"] is True
        assert result["candidates"] == 1
        with store.connect() as conn:
            row = conn.execute(
                "SELECT status, item_kind, reason FROM review_queue WHERE id = ?", (candidates[0]["id"],)
            ).fetchone()
        assert row is not None
        assert row["item_kind"] == "claim_conflict"
        assert row["status"] == "pending"
        assert "方向相反" in row["reason"]

        # 用户标记已审阅后重扫，状态保留。
        with store.connect() as conn:
            conn.execute("UPDATE review_queue SET status = 'reviewed' WHERE id = ?", (candidates[0]["id"],))
        persist_claim_conflicts(store, candidates)
        with store.connect() as conn:
            status = conn.execute("SELECT status FROM review_queue WHERE id = ?", (candidates[0]["id"],)).fetchone()
        assert status["status"] == "reviewed"

    def test_stale_conflicts_are_purged(self, store: SemanticStore) -> None:
        candidates = self._seed_conflict(store)
        persist_claim_conflicts(store, candidates)
        # 一侧 claim 被删除后重扫，旧候选必须清理，且不再产生新候选。
        with store.connect() as conn:
            conn.execute("DELETE FROM claims WHERE id = 'claim-b'")
        result = scan_and_persist(store)
        assert result["candidates"] == 0
        with store.connect() as conn:
            remaining = conn.execute(
                "SELECT count(*) FROM review_queue WHERE item_kind = 'claim_conflict'"
            ).fetchone()[0]
        assert remaining == 0

    def test_scan_and_persist_end_to_end(self, store: SemanticStore) -> None:
        result = scan_and_persist(store)
        assert result["success"] is True
        assert result["candidates"] == 0
        self._seed_conflict(store)
        result = scan_and_persist(store)
        assert result["candidates"] == 1
        with store.connect() as conn:
            payload = json.loads(
                conn.execute(
                    "SELECT payload_json FROM review_queue WHERE item_kind = 'claim_conflict'"
                ).fetchone()[0]
            )
        assert payload["claim_a"] == "混合检索优于纯向量检索"
        assert payload["claim_b"] == "纯向量检索优于混合检索"
