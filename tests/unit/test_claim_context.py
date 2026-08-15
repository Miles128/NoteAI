"""Tests for claim-layer retrieval injected into RAG chat (P0 consumer)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sidecar.rag.claim_context import retrieve_claim_context
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
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status, user_edited)
               VALUES('claim-1', '混合检索优于纯向量检索', '该数据集', 'conclusion', 0.9, 'active', 0)"""
        )
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status, user_edited)
               VALUES('claim-2', '纯向量检索优于混合检索', '', 'conclusion', 0.8, 'active', 0)"""
        )
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status, user_edited)
               VALUES('claim-3', '增大上下文窗口可能降低召回精度', '', 'hypothesis', 0.7, 'active', 0)"""
        )
        for claim_id, block_id in (("claim-1", "block-1"), ("claim-2", "block-1"), ("claim-3", "block-2")):
            conn.execute(
                """INSERT INTO evidence(id, claim_id, block_id, quote_hash, status)
                   VALUES(?, ?, ?, 'qh', 'active')""",
                (f"evidence-{claim_id}", claim_id, block_id),
            )
        conn.execute(
            """INSERT INTO review_queue(id, item_kind, payload_json, reason, status, created_at)
               VALUES('conflict-1', 'claim_conflict', ?, '方向相反', 'pending', '2026-08-01T00:00:00Z')""",
            (
                json.dumps(
                    {
                        "claim_a_id": "claim-1",
                        "claim_b_id": "claim-2",
                        "claim_a": "混合检索优于纯向量检索",
                        "claim_b": "纯向量检索优于混合检索",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    store.save_claim_verification(
        "claim-1",
        verdict="supported",
        confidence=0.85,
        summary="多项评测显示混合检索更稳健",
        method="cli",
        agent="claude",
        sources=[{"url": "https://example.com/1", "title": "评测"}],
    )
    return ws


def test_no_semantic_db_returns_empty(tmp_path: Path) -> None:
    assert retrieve_claim_context(tmp_path / "empty-workspace", "混合检索怎么样？") == []


def test_missing_question_or_workspace_returns_empty(workspace: Path) -> None:
    assert retrieve_claim_context(workspace, "") == []
    assert retrieve_claim_context("", "混合检索怎么样？") == []


def test_hits_claim_with_verification(workspace: Path) -> None:
    items = retrieve_claim_context(workspace, "混合检索是不是比纯向量检索更好？")
    assert items, "应检索到混合检索相关命题"
    entry = items[0]
    assert entry["source_type"] == "claim"
    assert entry["claim_id"] == "claim-1"
    assert entry["file_path"] == "Notes/RAG.md"
    assert "混合检索优于纯向量检索" in entry["content"]
    assert "已证实 85%" in entry["content"]
    assert "多项评测显示混合检索更稳健" in entry["content"]
    assert "知识库结论·已证实" in entry["source_label"]


def test_conflict_disclosure_in_content(workspace: Path) -> None:
    items = retrieve_claim_context(workspace, "混合检索和纯向量检索哪个好？")
    entry = next(item for item in items if item["claim_id"] == "claim-1")
    assert "存在矛盾" in entry["source_label"]
    assert "纯向量检索优于混合检索" in entry["content"]
    entry_b = next(item for item in items if item["claim_id"] == "claim-2")
    assert "混合检索优于纯向量检索" in entry_b["content"]


def test_topic_filter(workspace: Path) -> None:
    items = retrieve_claim_context(workspace, "上下文窗口对召回率有什么影响？", topics=["LLM > 上下文"])
    assert items
    assert all(item["topic"] == "LLM > 上下文" for item in items)
    # 主题过滤后不应命中 RAG 主题的命题。
    assert "混合检索" not in items[0]["content"]


def test_unverified_claim_label(workspace: Path) -> None:
    items = retrieve_claim_context(workspace, "增大上下文窗口会影响什么？")
    assert items
    assert all("尚未联网核查" in item["content"] for item in items)


def test_limit_respected(workspace: Path) -> None:
    items = retrieve_claim_context(workspace, "检索 混合 上下文 召回率 向量", limit=1)
    assert len(items) == 1


def test_irrelevant_question_returns_empty(workspace: Path) -> None:
    assert retrieve_claim_context(workspace, "今天天气怎么样") == []


def test_latest_verifications_for_claims_batches_single_query(workspace: Path) -> None:
    """批量验证查询：多 claim 一次取最新验证（N+1 → 1）。"""
    store = SemanticStore(workspace)
    store.save_claim_verification(
        "claim-2",
        verdict="refuted",
        confidence=0.9,
        summary="后续评测推翻该结论",
        method="cli",
        agent="claude",
        sources=[],
    )
    # claim-2 的第二次验证应覆盖首次（若存在），claim-3 无验证
    out = store.claims.latest_verifications_for_claims(["claim-1", "claim-2", "claim-3"])
    assert set(out) == {"claim-1", "claim-2"}
    assert out["claim-1"]["verdict"] == "supported"
    assert out["claim-1"]["confidence"] == 0.85
    assert out["claim-2"]["verdict"] == "refuted"
    assert out["claim-2"]["summary"] == "后续评测推翻该结论"
    assert out["claim-2"]["sources"] == []


def test_latest_verifications_for_claims_empty_input(workspace: Path) -> None:
    store = SemanticStore(workspace)
    assert store.claims.latest_verifications_for_claims([]) == {}
