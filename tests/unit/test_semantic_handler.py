from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sidecar.handlers.semantic_handler import SemanticHandler
from sidecar.semantic.store import SemanticStore

from config import config


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
        conn.execute("INSERT INTO entities VALUES('entity-2', '无来源实体', 'product', '', 0.4, 'active')")
        conn.execute("INSERT INTO entities VALUES('entity-3', 'BM25', 'algorithm', '', 0.85, 'active')")
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


def test_entity_quality_is_snapshot_only_and_reviewable(semantic_handler: SemanticHandler) -> None:
    quality = semantic_handler._get_workbench({"tab": "quality", "status": "pending"})

    assert quality["success"] is True
    assert quality["counts"]["isolated"] == 1
    assert quality["counts"]["missing_source"] == 2
    assert quality["counts"]["low_confidence"] == 1
    assert quality["counts"]["duplicate_candidate"] == 2
    duplicate = next(item for item in quality["items"] if item["rule"] == "duplicate_candidate")
    assert duplicate["entity_name"] == "BM25"
    reviewed = semantic_handler._review_entity_quality({"id": duplicate["id"], "status": "reviewed"})
    pending_after = semantic_handler._get_workbench({"tab": "quality", "status": "pending"})
    history = semantic_handler._get_workbench({"tab": "quality", "status": "reviewed"})

    assert reviewed["success"] is True
    assert all(item["id"] != duplicate["id"] for item in pending_after["items"])
    assert history["items"][0]["id"] == duplicate["id"]
    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        audit = conn.execute("SELECT action FROM semantic_audit_log WHERE object_kind = 'entity_quality'").fetchone()
    assert audit["action"] == "review_quality"


def test_entity_merge_preview_is_read_only(semantic_handler: SemanticHandler) -> None:
    preview = semantic_handler._get_entity_merge_preview({"source_id": "entity-1", "target_id": "entity-3"})

    assert preview["success"] is True
    assert preview["source"]["canonical_name"] == "BM25"
    assert preview["impact"]["entity-1"]["mentions"] == 1
    assert "不会修改" in preview["message"]


def test_entity_merge_requires_confirmation_and_preserves_mentions(semantic_handler: SemanticHandler) -> None:
    denied = semantic_handler._merge_entities({"source_id": "entity-1", "target_id": "entity-3"})
    merged = semantic_handler._merge_entities({"source_id": "entity-1", "target_id": "entity-3", "confirmed": True})
    entities = semantic_handler._get_workbench({"tab": "entities"})
    detail = semantic_handler._get_detail({"kind": "entity", "id": "entity-3"})

    assert denied["success"] is False
    assert merged["success"] is True
    assert entities["total"] == 2
    assert detail["item"]["sources"][0]["path"] == "Notes/AI/RAG.md"
    assert "BM25" not in detail["item"]["aliases"]
    assert detail["item"]["audit"][0]["action"] == "merge_entity"


def test_entity_merge_preserves_unrelated_self_relations_and_deduplicates_edges(
    semantic_handler: SemanticHandler,
) -> None:
    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO relations VALUES('self-other', 'entity-2', 'RELATED_TO', 'entity-2', 0.4, NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO relations VALUES('source-edge', 'entity-1', 'RELATED_TO', 'concept-1', 0.8, NULL, 'block-1')"
        )
        conn.execute(
            "INSERT INTO relations VALUES('target-edge', 'entity-3', 'RELATED_TO', 'concept-1', 0.9, NULL, 'block-1')"
        )

    merged = semantic_handler._merge_entities({"source_id": "entity-1", "target_id": "entity-3", "confirmed": True})

    assert merged["success"] is True
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM relations WHERE id = 'self-other'").fetchone()[0] == 1
        assert (
            conn.execute(
                """SELECT count(*) FROM relations
               WHERE source_id = 'entity-3' AND relation_type = 'RELATED_TO'
                 AND target_id = 'concept-1' AND block_id = 'block-1'"""
            ).fetchone()[0]
            == 1
        )


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
    excluded = semantic_handler._set_evidence_status({"id": "evidence-1", "status": "excluded"})
    claims = semantic_handler._get_workbench({"tab": "claims"})
    restored = semantic_handler._set_evidence_status({"id": "evidence-1", "status": "active"})
    alias = semantic_handler._add_entity_alias({"id": "entity-1", "alias": "Okapi BM25"})
    entity = semantic_handler._get_detail({"kind": "entity", "id": "entity-1"})

    assert excluded["success"] is True
    assert claims["total"] == 0
    assert restored["success"] is True
    assert alias["success"] is True
    assert entity["item"]["aliases"] == ["Okapi BM25"]
    assert entity["item"]["audit"][0]["action"] == "add_alias"


def test_topic_wiki_page_can_be_previewed_and_published(semantic_handler: SemanticHandler) -> None:
    preview = semantic_handler._get_topic_wiki_page({"topic": "AI > RAG"})
    published = semantic_handler._publish_topic_wiki_page({"topic": "AI > RAG"})

    assert preview["success"] is True
    assert "# AI > RAG" in preview["content"]
    assert published["success"] is True


def test_block_extraction_materializes_traceable_entity_concept_relation(
    semantic_handler: SemanticHandler,
) -> None:
    store = SemanticStore(semantic_handler.config.workspace_path)
    store.save_block_extraction(
        block_id="block-1",
        block_hash="replacement-hash",
        prompt_version=1,
        extracted_at="2026-07-19T10:00:00Z",
        concepts=[{"id": "concept-1", "canonical_name": "混合检索", "description": "组合检索方式", "confidence": 0.95}],
        entities=[
            {
                "id": "entity-1",
                "canonical_name": "BM25",
                "entity_type": "algorithm",
                "description": "关键词排序算法",
                "confidence": 0.9,
            }
        ],
        claims=[],
    )

    detail = semantic_handler._get_detail({"kind": "entity", "id": "entity-1"})
    context = semantic_handler._get_note_semantic_context({"path": "Notes/AI/RAG.md"})
    page = semantic_handler._get_object_wiki_page({"kind": "entity", "id": "entity-1"})

    assert detail["success"] is True
    assert detail["item"]["related"][0]["object_id"] == "concept-1"
    assert context["relations"][0]["source_name"] == "BM25"
    assert context["relations"][0]["target_name"] == "混合检索"
    assert "## 关联对象" in page["content"]
    assert "混合检索" in page["content"]


def test_automatic_materializer_refreshes_only_document_views(
    semantic_handler: SemanticHandler,
) -> None:
    from sidecar.semantic.materializer import materialize_documents

    store = SemanticStore(semantic_handler.config.workspace_path)
    result = materialize_documents(store, {"doc-1"})
    workspace = Path(semantic_handler.config.workspace_path)

    assert result["entities"] == 1
    assert result["concepts"] == 1
    assert result["topics"] == 1
    assert not result["failures"]
    entity_page = workspace / "wiki" / "semantic" / "实体.md"
    concept_page = workspace / "wiki" / "semantic" / "概念.md"
    assert entity_page.exists()
    assert concept_page.exists()
    assert "## BM25" in entity_page.read_text(encoding="utf-8")
    assert "## 混合检索" in concept_page.read_text(encoding="utf-8")
    assert not (workspace / "wiki" / "semantic" / "entities").exists()
    assert not (workspace / "wiki" / "semantic" / "concepts").exists()


def test_automatic_materializer_removes_page_when_old_object_loses_its_source(
    semantic_handler: SemanticHandler,
) -> None:
    from sidecar.semantic.materializer import materialize_documents

    store = SemanticStore(semantic_handler.config.workspace_path)
    previous = store.objects_for_document("doc-1")
    materialize_documents(store, {"doc-1"})
    target = Path(semantic_handler.config.workspace_path) / "wiki" / "semantic" / "实体.md"
    assert target.exists()
    with store.connect() as conn:
        conn.execute("DELETE FROM semantic_mentions WHERE object_id = 'entity-1' AND object_kind = 'entity'")

    result = materialize_documents(store, {"doc-1"}, previous_objects=previous)

    assert result["removed"]["entities"] == 1
    assert not result["failures"]
    assert target.exists()
    assert "## BM25" not in target.read_text(encoding="utf-8")


def test_aggregate_materializer_removes_only_generated_legacy_pages(
    semantic_handler: SemanticHandler,
) -> None:
    from sidecar.semantic.materializer import materialize_documents

    workspace = Path(semantic_handler.config.workspace_path)
    legacy = workspace / "wiki" / "semantic" / "entities"
    legacy.mkdir(parents=True)
    (legacy / "BM25.md").write_text("---\nsemantic_kind: entity\n---\n\n# BM25\n", encoding="utf-8")
    (legacy / "用户笔记.md").write_text("# 请保留\n", encoding="utf-8")

    result = materialize_documents(SemanticStore(workspace), {"doc-1"})

    assert not result["failures"]
    assert not (legacy / "BM25.md").exists()
    assert (legacy / "用户笔记.md").exists()
    assert (workspace / "wiki" / "semantic" / "实体.md").exists()


def test_automatic_materializer_refreshes_old_and_new_topics(
    semantic_handler: SemanticHandler,
) -> None:
    from sidecar.semantic.materializer import materialize_documents

    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        conn.execute("UPDATE documents SET topic = 'AI > 新主题' WHERE id = 'doc-1'")

    result = materialize_documents(store, {"doc-1"}, affected_topics={"AI > RAG"}, include_objects=False)
    workspace = Path(semantic_handler.config.workspace_path)

    assert result["topics"] == 2
    assert not result["failures"]
    assert (workspace / "wiki" / "semantic" / "AI" / "RAG_语义.md").exists()
    assert (workspace / "wiki" / "semantic" / "AI" / "新主题_语义.md").exists()


def test_automatic_materializer_retries_transient_database_lock(semantic_handler: SemanticHandler, monkeypatch) -> None:
    import sqlite3

    from sidecar.semantic import materializer

    store = SemanticStore(semantic_handler.config.workspace_path)
    original = materializer.materialize_object_collection
    calls = 0

    def locked_twice(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise sqlite3.OperationalError("database is locked")
        return original(*args, **kwargs)

    monkeypatch.setattr(materializer, "materialize_object_collection", locked_twice)
    monkeypatch.setattr(materializer.time, "sleep", lambda _delay: None)

    result = materializer.materialize_documents(
        store,
        set(),
        previous_objects=[{"kind": "entity", "id": "entity-1", "name": "BM25"}],
    )

    assert calls == 3
    assert result["entities"] == 1
    assert not result["failures"]


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


def test_full_compile_purges_deleted_documents_and_refreshes_object_pages(
    semantic_handler: SemanticHandler, monkeypatch
) -> None:
    from sidecar.semantic import compiler
    from sidecar.semantic.object_wiki import materialize_object_collection

    workspace = Path(semantic_handler.config.workspace_path)
    store = SemanticStore(workspace)
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('deleted-doc', 'Notes/AI/deleted.md', 'gone', 'Deleted', 'AI > Old', '2026-07-17T10:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO blocks VALUES(
               'deleted-block', 'deleted-doc', 'paragraph', '[]', 0,
               'stale source', 'stale-hash', 1, 1)"""
        )
        conn.execute("INSERT INTO entities VALUES('stale-entity', 'Stale', 'term', '', 0.7, 'active')")
        conn.execute("INSERT INTO semantic_mentions VALUES('stale-entity', 'entity', 'deleted-block')")
    materialize_object_collection(store, "entity")
    assert "Stale" in (workspace / "wiki" / "semantic" / "实体.md").read_text(encoding="utf-8")

    monkeypatch.setattr(
        compiler,
        "compile_semantic_batch",
        lambda *_args, **_kwargs: {
            "documents": 0,
            "blocks": 0,
            "extracted_blocks": 0,
            "claims": 0,
            "failed_blocks": 0,
            "pending_documents": 0,
            "failures": [],
            "materialized": {"entities": 0, "concepts": 0, "topics": 0},
        },
    )
    semantic_handler._server._send_job_update = lambda *_args, **_kwargs: None

    semantic_handler._run_full_compile(str(workspace), [])

    assert store.document("Notes/AI/deleted.md") is None
    assert "Stale" not in (workspace / "wiki" / "semantic" / "实体.md").read_text(encoding="utf-8")
