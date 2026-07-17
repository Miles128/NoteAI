from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import config
from sidecar.handlers.semantic_handler import SemanticHandler
from sidecar.semantic.store import SemanticStore


@pytest.fixture
def semantic_handler(tmp_path: Path):
    previous = config.workspace_path
    workspace = tmp_path / "workspace"
    (workspace / "Notes" / "AI").mkdir(parents=True)
    (workspace / "Notes" / "AI" / "RAG.md").write_text(
        "# RAG\n\n## 检索\n\n混合检索结合向量与关键词。\n", encoding="utf-8"
    )
    config.workspace_path = str(workspace)
    store = SemanticStore(workspace)
    store.initialize()
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-1', 'Notes/AI/RAG.md', 'hash', 'RAG', 'AI > RAG', '2026-07-17T10:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-1', 'doc-1', 'paragraph', '[\"检索\"]', 0,
                      '混合检索结合向量与关键词。', 'block-hash', 8, 8)"""
        )
        conn.execute("INSERT INTO concepts VALUES('concept-1', '混合检索', '组合检索方式', 0.95, 'active')")
        conn.execute("INSERT INTO entities VALUES('entity-1', 'BM25', 'algorithm', '关键词排序算法', 0.9, 'active')")
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
               VALUES('claim-1', '混合检索结合向量与关键词。', 'RAG',
                      'conclusion', 0.92, 'active')"""
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash)
               VALUES('evidence-1', 'claim-1', 'block-1', 'quote-hash')"""
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('concept-1', 'concept', 'block-1')")
        conn.execute("INSERT INTO semantic_mentions VALUES('entity-1', 'entity', 'block-1')")
        conn.execute(
            """INSERT INTO review_queue(id, item_kind, payload_json, reason, status, created_at)
               VALUES('conflict-1', 'claim_conflict', '{"claim_a":"A","claim_b":"B"}',
                      '数值不一致', 'pending', '2026-07-17T10:01:00Z')"""
        )
    (workspace / ".links.json").write_text(
        json.dumps(
            {
                "links": [
                    {"from": "Notes/AI/RAG.md", "to": "Notes/AI/BM25.md", "reason": "概念相关", "status": "confirmed"},
                    {"from": "Notes/AI/BM25.md", "to": "Notes/AI/RAG.md", "reason": "反向引用", "status": "confirmed"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    handler = SemanticHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))
    yield handler
    config.workspace_path = previous


def test_overview_and_claim_evidence_are_real(semantic_handler: SemanticHandler) -> None:
    overview = semantic_handler._get_workbench({"tab": "overview"})
    claims = semantic_handler._get_workbench({"tab": "claims", "query": "混合"})

    assert overview["success"] is True
    assert overview["overview"]["claims"] == 1
    assert overview["overview"]["evidence"] == 1
    assert overview["overview"]["source_documents"] == 1
    assert overview["overview"]["uncompiled_documents"] == 0
    assert claims["total"] == 1
    assert claims["items"][0]["claim_type"] == "conclusion"
    assert claims["items"][0]["evidence"][0]["path"] == "Notes/AI/RAG.md"
    assert claims["items"][0]["evidence"][0]["heading_path"] == ["检索"]


def test_concepts_entities_and_bidirectional_links(semantic_handler: SemanticHandler) -> None:
    concepts = semantic_handler._get_workbench({"tab": "concepts"})
    entities = semantic_handler._get_workbench({"tab": "entities"})
    links = semantic_handler._get_workbench({"tab": "links"})

    assert concepts["items"][0]["mention_count"] == 1
    assert entities["items"][0]["source_count"] == 1
    assert links["total"] == 2
    assert all(item["has_reverse"] for item in links["items"])


def test_conflict_review_changes_only_review_status(semantic_handler: SemanticHandler) -> None:
    pending = semantic_handler._get_workbench({"tab": "conflicts", "status": "pending"})
    reviewed = semantic_handler._review_conflict({"id": "conflict-1", "status": "reviewed"})
    history = semantic_handler._get_workbench({"tab": "conflicts", "status": "reviewed"})
    claims = semantic_handler._get_workbench({"tab": "claims"})

    assert pending["total"] == 1
    assert reviewed["success"] is True
    assert history["items"][0]["id"] == "conflict-1"
    assert claims["total"] == 1


def test_claim_can_be_edited_deleted_and_restored_with_audit(
    semantic_handler: SemanticHandler,
) -> None:
    edited = semantic_handler._update_claim(
        {
            "id": "claim-1",
            "statement": "混合检索通常优于单一路径。",
            "scope": "检索质量",
            "claim_type": "conclusion",
        }
    )
    deleted = semantic_handler._set_claim_status({"id": "claim-1", "status": "deleted"})
    active = semantic_handler._get_workbench({"tab": "claims"})
    history = semantic_handler._get_workbench({"tab": "claims", "status": "deleted"})
    restored = semantic_handler._set_claim_status({"id": "claim-1", "status": "active"})
    detail = semantic_handler._get_detail({"kind": "claim", "id": "claim-1"})

    assert edited["success"] is True
    assert deleted["success"] is True
    assert active["total"] == 0
    assert history["total"] == 1
    assert restored["success"] is True
    assert detail["item"]["statement"] == "混合检索通常优于单一路径。"
    assert [entry["action"] for entry in detail["item"]["audit"]] == [
        "restore",
        "delete",
        "edit",
    ]


def test_evidence_exclusion_and_entity_alias_are_audited(
    semantic_handler: SemanticHandler,
) -> None:
    excluded = semantic_handler._set_evidence_status(
        {"id": "evidence-1", "status": "excluded"}
    )
    claims = semantic_handler._get_workbench({"tab": "claims"})
    restored = semantic_handler._set_evidence_status(
        {"id": "evidence-1", "status": "active"}
    )
    alias = semantic_handler._add_entity_alias({"id": "entity-1", "alias": "Okapi BM25"})
    entity = semantic_handler._get_detail({"kind": "entity", "id": "entity-1"})

    assert excluded["success"] is True
    assert claims["total"] == 0
    assert restored["success"] is True
    assert alias["success"] is True
    assert entity["item"]["aliases"] == ["Okapi BM25"]
    assert entity["item"]["audit"][0]["action"] == "add_alias"


def test_unknown_tab_is_rejected(semantic_handler: SemanticHandler) -> None:
    result = semantic_handler._get_workbench({"tab": "everything"})
    assert result["success"] is False


def test_semantic_detail_returns_source_blocks(semantic_handler: SemanticHandler) -> None:
    concept = semantic_handler._get_detail({"kind": "concept", "id": "concept-1"})
    claim = semantic_handler._get_detail({"kind": "claim", "id": "claim-1"})

    assert concept["success"] is True
    assert concept["item"]["sources"][0]["path"] == "Notes/AI/RAG.md"
    assert claim["item"]["sources"][0]["excerpt"] == "混合检索结合向量与关键词。"
    assert claim["item"]["claim_type"] == "conclusion"


def test_start_full_compile_uses_every_note(semantic_handler: SemanticHandler) -> None:
    captured = {}

    def fake_start(task_name, target, args=(), kwargs=None, kind="task", label=None):
        captured.update(task_name=task_name, target=target, args=args, kind=kind, label=label)
        return True

    semantic_handler._server._start_task = fake_start
    result = semantic_handler._start_full_compile({})

    assert result["success"] is True
    assert result["total_documents"] == 1
    assert len(captured["args"][1]) == 1
    assert captured["kind"] == "semantic_compile"
