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
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('concept-1', '混合检索', '组合检索方式', 0.95, 'active')"
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('entity-1', 'BM25', 'algorithm', '关键词排序算法', 0.9, 'active')"
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('entity-2', '无来源实体', 'product', '', 0.4, 'active')"
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('entity-3', 'BM25', 'algorithm', '', 0.85, 'active')"
        )
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
        # Entity → Concept co-occurrence relation (target endpoint is a concept, not an entity)
        conn.execute(
            """INSERT INTO relations(id, source_id, relation_type, target_id, confidence, evidence_id, block_id)
               VALUES('rel-1', 'entity-1', 'RELATED_TO', 'concept-1', 0.9, NULL, 'block-1') """
        )
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
    # entity-1 通过实体→概念共现关系（rel-1）已建立受控关系，不再孤立
    assert quality["counts"]["isolated"] == 0
    assert quality["counts"]["missing_source"] == 2
    assert quality["counts"]["low_confidence"] == 1
    assert quality["counts"]["duplicate_candidate"] == 2
    # An entity→concept relation is NOT dangling: concept endpoints are legitimate.
    assert quality["counts"]["dangling_relation"] == 0
    assert all(item["rule"] != "dangling_relation" for item in quality["items"])
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
    # Use deep intensity so the assertion focuses on the merge result, not the
    # default confidence filter (entity-2 has 0.4 and is hidden in standard).
    entities = semantic_handler._get_workbench({"tab": "entities", "intensity": "deep"})
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


def test_cross_kind_duplicate_rule_preview_and_batch_enqueue(semantic_handler: SemanticHandler) -> None:
    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('concept-2', 'BM25', '关键词检索算法', 0.9, 'active')"
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('concept-2', 'concept', 'block-1')")

    quality = semantic_handler._get_workbench({"tab": "quality", "status": "pending"})
    cross = [item for item in quality["items"] if item["rule"] == "cross_kind_duplicate"]
    assert len(cross) == 2  # entity-1 与 entity-3 都同名命中概念
    assert cross[0]["entity_name"] == "BM25"
    assert cross[0]["candidate_names"] == ["BM25"]
    assert cross[0]["candidate_kinds"] == ["concept"]
    assert quality["counts"]["cross_kind_duplicate"] == 2

    # 批量入队
    result = semantic_handler._enqueue_cross_kind_merges({})
    assert result["success"] is True
    assert result["count"] == 2
    with store.connect() as conn:
        queued = conn.execute(
            "SELECT count(*) FROM review_queue WHERE item_kind = 'entity_quality'"
            " AND status = 'pending' AND payload_json LIKE '%cross_kind_duplicate%'"
        ).fetchone()[0]
        assert queued == 2

    # preview 支持概念 target
    preview = semantic_handler._get_entity_merge_preview({"source_id": "entity-1", "target_id": "concept-2"})
    assert preview["success"] is True
    assert preview["source"]["kind"] == "entity"
    assert preview["target"]["kind"] == "concept"
    assert preview["impact"]["concept-2"]["mentions"] == 1


def test_claims_batch_verify_writes_verifications(semantic_handler: SemanticHandler) -> None:
    """内置 LLM 批量核查：verdict 写入 claim_verifications（method='llm'）。"""
    from sidecar.semantic.claim_verifier import parse_batch_verification_json, verify_claims_batch

    parsed = parse_batch_verification_json(
        '```json\n{"results": [{"claim_id": 1, "verdict": "supported", "confidence": 0.9}, '
        '{"claim_id": 2, "verdict": "refuted", "confidence": 0.7, "reason": "有反例"}]}\n```'
    )
    assert parsed[1]["verdict"] == "supported"
    assert parsed[2]["verdict"] == "refuted" and parsed[2]["reason"] == "有反例"
    # 非法 verdict 被丢弃
    assert 3 not in parse_batch_verification_json('{"results": [{"claim_id": 3, "verdict": "nope"}]}')

    store = SemanticStore(semantic_handler.config.workspace_path)

    def fake_llm(_prompt: str) -> str:
        return '{"results": [{"claim_id": 1, "verdict": "refuted", "confidence": 0.8, "reason": "反例"}]}'

    claims = [{"id": "claim-1", "statement": "混合检索结合向量与关键词。", "scope": "RAG"}]
    result = verify_claims_batch(store, claims, llm_call=fake_llm)
    assert result["success"] is True
    assert result["stats"]["refuted"] == 1
    with store.connect() as conn:
        row = conn.execute(
            "SELECT verdict, confidence, method, agent, summary FROM claim_verifications WHERE claim_id = 'claim-1'"
        ).fetchone()
        assert row is not None
        assert row["verdict"] == "refuted"
        assert row["method"] == "llm"
        assert row["agent"] == "builtin"
        assert row["summary"] == "反例"


def test_claims_batch_verify_rpc_filters_by_scope(semantic_handler: SemanticHandler) -> None:
    """RPC 入口：scope 过滤 + limit，返回统计。"""
    from unittest.mock import patch

    with patch("sidecar.semantic.claim_verifier.verify_claims_batch") as mock_verify:
        mock_verify.return_value = {"success": True, "total": 1, "outcomes": [], "stats": {"supported": 1}}
        result = semantic_handler._verify_claims_batch({"scope": "RAG", "limit": 5})
        assert result["success"] is True
        called_claims = mock_verify.call_args[0][1]
        assert len(called_claims) <= 5
        assert all("rag" in str(c.get("scope", "")).casefold() for c in called_claims)


def test_quality_flags_lowercase_english_word_entities(semantic_handler: SemanticHandler) -> None:
    """type=other 的全小写普通英文词实体被标记为疑似分类错误。"""
    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('entity-4', 'bundled', 'other', '描述', 0.9, 'active')"
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('entity-5', 'pandas', 'product', '库', 0.9, 'active')"
        )

    quality = semantic_handler._get_workbench({"tab": "quality", "status": "pending"})
    flagged = [item for item in quality["items"] if item["rule"] == "unlikely_entity_name"]
    assert [item["entity_name"] for item in flagged] == ["bundled"]
    assert quality["counts"]["unlikely_entity_name"] == 1


def test_cross_kind_merge_moves_mentions_and_relations_into_target_kind(
    semantic_handler: SemanticHandler,
) -> None:
    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('concept-2', 'BM25', '关键词检索算法', 0.9, 'active')"
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('concept-2', 'concept', 'block-1')")

    merged = semantic_handler._merge_entities(
        {"source_id": "entity-1", "target_id": "concept-2", "confirmed": True}
    )

    assert merged["success"] is True
    assert "概念" in merged["message"]
    with store.connect() as conn:
        # 源实体行已删除，目标概念保留
        assert conn.execute("SELECT count(*) FROM entities WHERE id = 'entity-1'").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM concepts WHERE id = 'concept-2'").fetchone()[0] == 1
        # mentions 转移并改写 object_kind
        moved = conn.execute(
            "SELECT count(*) FROM semantic_mentions WHERE object_id = 'concept-2' AND object_kind = 'concept'"
        ).fetchone()[0]
        assert moved == 1
        # fixture 的 rel-1（entity-1 → concept-1）端点改指向概念 concept-2
        relation = conn.execute(
            "SELECT * FROM relations WHERE source_id = 'concept-2' AND target_id = 'concept-1'"
        ).fetchone()
        assert relation is not None
        assert relation["relation_type"] == "RELATED_TO"
        # 无残留实体 mentions
        assert (
            conn.execute(
                "SELECT count(*) FROM semantic_mentions WHERE object_id = 'entity-1' AND object_kind = 'entity'"
            ).fetchone()[0]
            == 0
        )


def test_cross_kind_resolver_merges_concept_into_entity(semantic_handler: SemanticHandler) -> None:
    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('concept-2', 'BM25', '关键词检索算法', 0.9, 'active')"
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('concept-2', 'concept', 'block-1')")
    queued = semantic_handler._enqueue_cross_kind_merges({})
    assert queued["success"] is True and queued["count"] >= 1

    def fake_llm(_prompt: str) -> str:
        return '```json\n{"pairs": [{"pair_id": 1, "verdict": "merge_entity", "reason": "same object"}]}\n```'

    from sidecar.semantic.cross_kind_resolver import resolve_cross_kind_merges

    result = resolve_cross_kind_merges(store, llm_call=fake_llm)
    assert result["success"] is True
    assert result["stats"]["merge_entity"] == 1
    with store.connect() as conn:
        # 概念并入实体：概念行已删、实体保留、该对 issue 已审（另一对因 entity-3 存在而 skip）
        assert conn.execute("SELECT count(*) FROM concepts WHERE id = 'concept-2'").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM entities WHERE id = 'entity-1' AND status = 'active'").fetchone()[0] == 1
        pending = conn.execute(
            "SELECT count(*) FROM review_queue WHERE item_kind = 'entity_quality' AND status = 'pending'"
        ).fetchone()[0]
        assert pending == 1


def test_cross_kind_resolver_keeps_distinct_pairs_and_parses_partial_batch(
    semantic_handler: SemanticHandler,
) -> None:
    from sidecar.semantic.cross_kind_resolver import parse_verdicts, resolve_cross_kind_merges

    parsed = parse_verdicts('前文 {"pairs": [{"pair_id": 2, "verdict": "keep_both"}, {"pair_id": 3, "verdict": "merge_concept", "reason": "x"}]} 后文')
    assert parsed == {2: "keep_both", 3: "merge_concept"}

    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('concept-2', 'BM25', '关键词检索算法', 0.9, 'active')"
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('concept-2', 'concept', 'block-1')")
    semantic_handler._enqueue_cross_kind_merges({})

    def fake_llm(_prompt: str) -> str:
        return '{"pairs": [{"pair_id": 1, "verdict": "keep_both"}]}'

    result = resolve_cross_kind_merges(store, llm_call=fake_llm)
    assert result["stats"]["keep_both"] == 1
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM concepts WHERE status = 'active'").fetchone()[0] == 2
        assert conn.execute("SELECT count(*) FROM entities WHERE status = 'active'").fetchone()[0] == 3
        # keep_both 的对已审，另一对（entity-3 变体）因未裁决而保留 pending
        pending = conn.execute(
            "SELECT count(*) FROM review_queue WHERE item_kind = 'entity_quality' AND status = 'pending'"
        ).fetchone()[0]
        assert pending == 1


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
    workspace = Path(semantic_handler.config.workspace_path)

    assert preview["success"] is True
    assert "# RAG" in preview["content"]
    assert "## 已发布结论" in preview["content"]
    assert published["success"] is True
    merged = workspace / "wiki" / "semantic" / "AI_语义.md"
    assert merged.exists()
    assert "## RAG" in merged.read_text(encoding="utf-8")
    assert not (workspace / "wiki" / "semantic" / "AI" / "RAG_语义.md").exists()


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


def test_extraction_dedups_variant_spellings_into_existing_object(
    semantic_handler: SemanticHandler,
) -> None:
    """抽取时变体写法（括号注释/空白/大小写差异）必须合并到已有对象。

    第二次抽取出现的变体名不能新建行：ID 复用已有对象，mentions 挂到
    同一 ID，描述/置信度走 upsert 合并而 canonical_name 保持原名。
    """
    store = SemanticStore(semantic_handler.config.workspace_path)
    with store.connect() as conn:
        for i in (1, 2):
            conn.execute(
                """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                      content, content_hash, start_line, end_line)
                   VALUES(?, 'doc-1', 'paragraph', '["检索"]', ?,
                          'block content', ?, ?, ?)""",
                (f"block-v-{i}", i, f"hash-v-{i}", 30 + i, 30 + i),
            )

    store.save_block_extraction(
        block_id="block-v-1",
        block_hash="hash-v-1",
        prompt_version=1,
        extracted_at="2026-07-19T10:00:00Z",
        concepts=[{"id": "concept-rag-1", "canonical_name": "RAG", "description": "基础描述", "confidence": 0.9}],
        entities=[
            {
                "id": "entity-rag-1",
                "canonical_name": "RAG",
                "entity_type": "protocol",
                "description": "",
                "confidence": 0.8,
            }
        ],
        claims=[],
    )
    # 第二个块抽到同一对象的不同变体：括号注释、空格、大小写均不同
    store.save_block_extraction(
        block_id="block-v-2",
        block_hash="hash-v-2",
        prompt_version=1,
        extracted_at="2026-07-19T10:01:00Z",
        concepts=[
            {
                "id": "concept-rag-2",
                "canonical_name": "RAG（Retrieval-Augmented Generation）",
                "description": "更长的描述",
                "confidence": 0.95,
            }
        ],
        entities=[
            {
                "id": "entity-rag-2",
                "canonical_name": "R A G",
                "entity_type": "algorithm",
                "description": "混合检索",
                "confidence": 0.9,
            }
        ],
        claims=[],
    )

    with store.connect() as conn:
        crows = conn.execute(
            "SELECT id, canonical_name, confidence FROM concepts WHERE id LIKE 'concept-rag-%'"
        ).fetchall()
        assert len(crows) == 1
        assert crows[0]["id"] == "concept-rag-1"
        assert crows[0]["canonical_name"] == "RAG"  # 原名保留，不被变体覆盖
        assert crows[0]["confidence"] == 0.95  # 置信度取 max
        cmentions = conn.execute(
            "SELECT object_id, block_id FROM semantic_mentions WHERE object_kind='concept' AND object_id LIKE 'concept-rag-%' ORDER BY block_id"
        ).fetchall()
        assert [(m["object_id"], m["block_id"]) for m in cmentions] == [
            ("concept-rag-1", "block-v-1"),
            ("concept-rag-1", "block-v-2"),
        ]
        erows = conn.execute(
            "SELECT id, canonical_name, entity_type, confidence FROM entities WHERE id LIKE 'entity-rag-%'"
        ).fetchall()
        assert len(erows) == 1
        assert erows[0]["id"] == "entity-rag-1"
        assert erows[0]["entity_type"] == "protocol"  # entity_type 不被变体覆盖
        assert erows[0]["confidence"] == 0.9
        ementions = conn.execute(
            "SELECT object_id, block_id FROM semantic_mentions WHERE object_kind='entity' AND object_id LIKE 'entity-rag-%' ORDER BY block_id"
        ).fetchall()
        assert [(m["object_id"], m["block_id"]) for m in ementions] == [
            ("entity-rag-1", "block-v-1"),
            ("entity-rag-1", "block-v-2"),
        ]


def test_automatic_materializer_refreshes_only_document_views(
    semantic_handler: SemanticHandler,
) -> None:
    from sidecar.semantic.materializer import materialize_documents

    store = SemanticStore(semantic_handler.config.workspace_path)
    # 聚合页只收录至少出现 3 次的对象：给 BM25/混合检索补足三个来源块
    with store.connect() as conn:
        for i in (2, 3):
            conn.execute(
                """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                      content, content_hash, start_line, end_line)
                   VALUES(?, 'doc-1', 'paragraph', '["检索"]', ?,
                          'BM25 是混合检索的核心。', ?, ?, ?)""",
                (f"block-{i}", i, f"block-hash-{i}", 8 + i, 8 + i),
            )
            conn.execute("INSERT INTO semantic_mentions VALUES('concept-1', 'concept', ?)", (f"block-{i}",))
            conn.execute("INSERT INTO semantic_mentions VALUES('entity-1', 'entity', ?)", (f"block-{i}",))
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
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-2', 'Notes/AI/RAG2.md', 'hash2', 'RAG2', 'AI > RAG',
                      '2026-07-17T10:00:00Z') """
        )

    result = materialize_documents(store, {"doc-1"}, affected_topics={"AI > RAG"}, include_objects=False)
    workspace = Path(semantic_handler.config.workspace_path)

    assert result["topics"] == 2
    assert result["wiki_pages"] == 1
    assert not result["failures"]
    merged = workspace / "wiki" / "semantic" / "AI_语义.md"
    assert merged.exists()
    content = merged.read_text(encoding="utf-8")
    assert "## RAG" in content
    assert "## 新主题" in content
    assert not (workspace / "wiki" / "semantic" / "AI" / "RAG_语义.md").exists()
    assert not (workspace / "wiki" / "semantic" / "AI" / "新主题_语义.md").exists()


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
        conn.execute(
            """INSERT INTO blocks VALUES(
               'deleted-block-2', 'deleted-doc', 'paragraph', '[]', 1,
               'stale source 2', 'stale-hash-2', 2, 2)"""
        )
        conn.execute(
            """INSERT INTO blocks VALUES(
               'deleted-block-3', 'deleted-doc', 'paragraph', '[]', 2,
               'stale source 3', 'stale-hash-3', 3, 3)"""
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('stale-entity', 'Stale', 'term', '', 0.7, 'active')"
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('stale-entity', 'entity', 'deleted-block')")
        conn.execute("INSERT INTO semantic_mentions VALUES('stale-entity', 'entity', 'deleted-block-2')")
        conn.execute("INSERT INTO semantic_mentions VALUES('stale-entity', 'entity', 'deleted-block-3')")
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
            "rejected_claims": 0,
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


def test_purge_missing_documents_removes_records_outside_compile_set(
    semantic_handler: SemanticHandler,
) -> None:
    """磁盘存在但不在编译集合内的记录（如隐藏目录残留）也会被清理。"""
    from utils.note_scanner import iter_note_files

    workspace = Path(semantic_handler.config.workspace_path)
    hidden = workspace / "Notes" / ".workbuddy" / "memory.md"
    hidden.parent.mkdir(parents=True)
    hidden.write_text("hidden", encoding="utf-8")
    store = SemanticStore(workspace)
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('hidden-doc', 'Notes/.workbuddy/memory.md', 'h', 'Hidden', '',
                      '2026-07-17T10:00:00Z') """
        )

    keep_paths = iter_note_files(workspace)
    assert all(".workbuddy" not in p.parts for p in keep_paths)

    topics = store.purge_missing_documents(keep_paths=keep_paths)

    assert store.document("Notes/.workbuddy/memory.md") is None
    # 编译集合内的正常文档不受影响
    assert store.document("Notes/AI/RAG.md") is not None
    assert topics == []


def test_purge_missing_documents_without_keep_paths_keeps_existing_files(
    semantic_handler: SemanticHandler,
) -> None:
    """不传 keep_paths 时保持原行为：磁盘存在的记录不被清理。"""
    workspace = Path(semantic_handler.config.workspace_path)
    store = SemanticStore(workspace)

    topics = store.purge_missing_documents()

    assert store.document("Notes/AI/RAG.md") is not None
    assert topics == []


def test_get_semantic_changes_is_read_only_and_validates_params(semantic_handler: SemanticHandler) -> None:
    result = semantic_handler._get_changes({"days": 7, "limit": 10})
    assert result["success"] is True
    assert result["days"] == 7
    assert isinstance(result["counts"], list)
    assert isinstance(result["items"], list)
    assert result["total"] == 0

    assert semantic_handler._get_changes({"object_kind": "relation"})["success"] is False

    clamped = semantic_handler._get_changes({"days": "999"})
    assert clamped["success"] is True
    assert clamped["days"] == 90

    store = SemanticStore(config.workspace_path)
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO semantic_change_log(
                   id, change_kind, object_kind, object_id, label, detail_json,
                   source_path, topic, created_at
               ) VALUES('chg-1', 'added', 'claim', 'claim-x', '新命题', '{}',
                        'Notes/AI/RAG.md', 'AI > RAG', datetime('now'))"""
        )
    listed = semantic_handler._get_changes({"days": 7})
    assert listed["total"] == 1
    assert listed["items"][0]["label"] == "新命题"
    assert listed["counts"] == [{"change_kind": "added", "object_kind": "claim", "count": 1}]


def test_get_semantic_changes_repairs_legacy_store_without_change_log(
    semantic_handler: SemanticHandler,
) -> None:
    """Workspaces created before the change log table must not crash the digest.

    Regression: a legacy ``semantic.db`` predating ``semantic_change_log``
    raised ``sqlite3.OperationalError: no such table`` on startup because the
    read-only workbench never re-runs schema initialization.
    """
    store = SemanticStore(config.workspace_path)
    with store.connect() as conn:
        conn.execute("DROP TABLE semantic_change_log")
        conn.execute("DROP INDEX IF EXISTS idx_semantic_change_created")

    result = semantic_handler._get_changes({"days": 7})

    assert result["success"] is True
    assert result["counts"] == []
    assert result["items"] == []
    assert result["total"] == 0

    # The digest must have repaired the schema in place.
    with store.connect() as conn:
        tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "semantic_change_log" in tables


def test_change_log_read_methods_self_heal_legacy_store(tmp_path: Path) -> None:
    """Store-level read APIs create the missing table instead of raising."""
    workspace = tmp_path / "legacy-workspace"
    store = SemanticStore(workspace)
    store.initialize()
    with store.connect() as conn:
        conn.execute("DROP TABLE semantic_change_log")
        conn.execute("DROP INDEX IF EXISTS idx_semantic_change_created")

    assert store.change_counts(days=7) == []
    items, total = store.recent_changes(days=7)
    assert items == []
    assert total == 0

    # After repair, writes and reads must work end to end.
    with store.connect() as conn:
        SemanticStore._record_change(
            conn,
            change_kind="added",
            object_kind="claim",
            object_id="claim-1",
            label="测试命题",
        )
    items, total = store.recent_changes(days=7)
    assert total == 1
    assert items[0]["label"] == "测试命题"


def test_workbench_intensity_filters_confidence(semantic_handler: SemanticHandler) -> None:
    """Intensity light/standard/deep must filter claims and objects by confidence."""
    store = semantic_handler._store()
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('entity-4', '中置信实体', 'concept_type', '描述', 0.62, 'active')"
        )
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status)
               VALUES('claim-2', '低置信命题。', 'RAG', 'hypothesis', 0.31, 'active')"""
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash)
               VALUES('evidence-2', 'claim-2', 'block-1', 'quote-hash-2')"""
        )

    entities_deep = semantic_handler._get_workbench({"tab": "entities", "intensity": "deep"})
    entities_standard = semantic_handler._get_workbench({"tab": "entities", "intensity": "standard"})
    entities_light = semantic_handler._get_workbench({"tab": "entities", "intensity": "light"})
    claims_deep = semantic_handler._get_workbench({"tab": "claims", "intensity": "deep"})
    claims_light = semantic_handler._get_workbench({"tab": "claims", "intensity": "light"})

    assert entities_deep["total"] == 4
    assert entities_standard["total"] == 3  # 0.4 被过滤
    assert entities_light["total"] == 2  # 0.4 与 0.62 被过滤
    assert claims_deep["total"] == 2
    assert claims_light["total"] == 1  # 0.31 被过滤

    # 未知强度回退到标准强度
    fallback = semantic_handler._get_workbench({"tab": "entities", "intensity": "ultra"})
    assert fallback["total"] == entities_standard["total"]


def test_low_frequency_objects_are_degraded_outside_deep_mode(semantic_handler: SemanticHandler) -> None:
    """低频低置信对象（mention<2 且 confidence<0.6）默认隐藏，deep 可见、搜索可命中。"""
    store = semantic_handler._store()
    with store.connect() as conn:
        # 降级候选：0.55 置信 + 仅 1 次 mention
        conn.execute(
            """INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)
               VALUES('entity-5', '低频低置信实体', 'product', '描述', 0.55, 'active')"""
        )
        conn.execute("INSERT INTO semantic_mentions VALUES('entity-5', 'entity', 'block-1')")
        # 高频低置信：5 次 mention + 0.55 置信 → 不应被降级（条件需同时满足）
        conn.execute(
            """INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)
               VALUES('entity-6', '高频低置信实体', 'product', '描述', 0.55, 'active')"""
        )
        for block_id in ("block-1", "block-2", "block-3", "block-4", "block-5"):
            conn.execute(
                """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                      content, content_hash, start_line, end_line)
                   VALUES(?, 'doc-1', 'paragraph', '[]', 1, '内容', 'hash-' || ?, 9, 9)
                   ON CONFLICT(id) DO NOTHING""",
                (block_id, block_id),
            )
            conn.execute("INSERT OR IGNORE INTO semantic_mentions VALUES('entity-6', 'entity', ?)", (block_id,))

    entities_standard = semantic_handler._get_workbench({"tab": "entities", "intensity": "standard"})
    entities_deep = semantic_handler._get_workbench({"tab": "entities", "intensity": "deep"})
    entities_search = semantic_handler._get_workbench(
        {"tab": "entities", "intensity": "standard", "query": "低频低置信"}
    )

    names_standard = {item["canonical_name"] for item in entities_standard["items"]}
    assert "低频低置信实体" not in names_standard
    assert "高频低置信实体" in names_standard  # 仅低置信但高频 → 保留
    assert entities_standard["degraded_hidden"] == 1
    assert entities_deep["degraded_hidden"] == 0  # deep 不降级
    names_deep = {item["canonical_name"] for item in entities_deep["items"]}
    assert "低频低置信实体" in names_deep
    # 主动搜索仍可命中降级对象
    names_search = {item["canonical_name"] for item in entities_search["items"]}
    assert "低频低置信实体" in names_search
    assert entities_search["degraded_hidden"] == 0


def _mark_claim_failed(store: SemanticStore, block_id: str, error: str = "LLM 超时") -> None:
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO claim_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
               VALUES(?, 'block-hash', 4, 'failed', '2026-07-17T10:00:00Z', ?)""",
            (block_id, error),
        )


def test_retry_failed_blocks_no_failures(semantic_handler: SemanticHandler) -> None:
    result = semantic_handler._retry_failed_blocks({"claims_only": True})
    assert result["success"] is True
    assert result["failed_blocks"] == 0
    assert result["extracted_blocks"] == 0


def test_retry_failed_blocks_retries_and_completes(semantic_handler: SemanticHandler, monkeypatch) -> None:
    _mark_claim_failed(semantic_handler._store(), "block-1")
    calls: list[tuple[str, bool]] = []

    def fake_extract(store, doc_id, claims_only=False):
        calls.append((doc_id, claims_only))
        with store.connect() as conn:
            conn.execute(
                """UPDATE claim_extractions SET status='complete', error=NULL
                   WHERE block_id='block-1'"""
            )
        return {"success": True, "extracted": 1, "claims": 1, "failed": 0, "failures": []}

    monkeypatch.setattr("sidecar.semantic.extractor.extract_document_semantics", fake_extract)
    result = semantic_handler._retry_failed_blocks({"claims_only": True})
    assert result["success"] is True
    assert result["failed_blocks"] == 1
    assert result["documents"] == 1
    assert result["extracted_blocks"] == 1
    assert result["remaining_failed"] == 0
    assert calls == [("doc-1", True)]


def test_retry_failed_blocks_limit(semantic_handler: SemanticHandler, monkeypatch) -> None:
    with semantic_handler._store().connect() as conn:
        conn.execute(
            """INSERT INTO claim_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
               VALUES('block-1', 'block-hash', 4, 'failed', '2026-07-17T10:00:00Z', 'err-1')"""
        )
        for i in (2, 3):
            conn.execute(
                """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
                   VALUES(?, ?, 'hash', ?, '', '2026-07-17T10:00:00Z')""",
                (f"doc-{i}", f"Notes/AI/RAG{i}.md", f"RAG{i}"),
            )
            conn.execute(
                """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                      content, content_hash, start_line, end_line)
                   VALUES(?, ?, 'paragraph', '[]', 0, '内容', 'hash', 1, 1)""",
                (f"block-{i}", f"doc-{i}"),
            )
            conn.execute(
                """INSERT INTO claim_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
                   VALUES(?, 'block-hash', 4, 'failed', '2026-07-17T10:00:00Z', ?)""",
                (f"block-{i}", f"err-{i}"),
            )
    calls: list[str] = []

    def fake_extract(store, doc_id, claims_only=False):
        calls.append(doc_id)
        return {"success": True, "extracted": 0, "claims": 0, "failures": []}

    monkeypatch.setattr("sidecar.semantic.extractor.extract_document_semantics", fake_extract)
    result = semantic_handler._retry_failed_blocks({"claims_only": True, "limit": 1})
    assert result["failed_blocks"] == 1
    assert result["documents"] == 1
    assert len(calls) == 1
    # fake 不写库，剩余失败数保持原值。
    assert result["remaining_failed"] == 3


def test_retry_failed_blocks_reports_failure(semantic_handler: SemanticHandler, monkeypatch) -> None:
    _mark_claim_failed(semantic_handler._store(), "block-1", "解析失败")

    def fake_extract(store, doc_id, claims_only=False):
        return {
            "success": True,
            "extracted": 0,
            "claims": 0,
            "failures": [{"block_id": "block-1", "error": "解析失败"}],
        }

    monkeypatch.setattr("sidecar.semantic.extractor.extract_document_semantics", fake_extract)
    result = semantic_handler._retry_failed_blocks({"claims_only": True})
    assert result["failures"] == [{"document_id": "doc-1", "error": "解析失败"}]
    assert result["remaining_failed"] == 1


def test_retry_failed_blocks_full_mode_uses_block_extractions(semantic_handler: SemanticHandler, monkeypatch) -> None:
    with semantic_handler._store().connect() as conn:
        conn.execute(
            """INSERT INTO block_extractions(block_id, block_hash, prompt_version, status, extracted_at, error)
               VALUES('block-1', 'block-hash', 4, 'failed', '2026-07-17T10:00:00Z', '超时')"""
        )
    calls: list[bool] = []

    def fake_extract(store, doc_id, claims_only=False):
        calls.append(claims_only)
        with store.connect() as conn:
            conn.execute(
                """UPDATE block_extractions SET status='complete', error=NULL
                   WHERE block_id='block-1'"""
            )
        return {"success": True, "extracted": 1, "claims": 0, "failures": []}

    monkeypatch.setattr("sidecar.semantic.extractor.extract_document_semantics", fake_extract)
    result = semantic_handler._retry_failed_blocks({"claims_only": False})
    assert result["success"] is True
    assert result["failed_blocks"] == 1
    assert result["extracted_blocks"] == 1
    assert result["remaining_failed"] == 0
    assert calls == [False]
