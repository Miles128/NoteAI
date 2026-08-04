"""Tests for claim verification: CLI deep-research mode."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sidecar.handlers.semantic_handler import SemanticHandler
from sidecar.semantic.claim_verifier import (
    build_cli_research_prompt,
    parse_verification_json,
    verify_claim_via_cli,
)
from sidecar.semantic.store import SemanticStore

from config import config


@pytest.fixture
def store(tmp_path: Path):
    workspace = tmp_path / "workspace"
    semantic_store = SemanticStore(workspace)
    semantic_store.initialize()
    with semantic_store.connect() as conn:
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-1', 'Notes/AI.md', 'hash', 'AI', 'AI > RAG', '2026-08-01T00:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO documents(id, path, content_hash, title, topic, compiled_at)
               VALUES('doc-2', 'Notes/LLM.md', 'hash2', 'LLM', 'LLM > 上下文', '2026-08-01T00:00:00Z')"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-1', 'doc-1', 'paragraph', '["检索"]', 0, '内容。', 'block-hash', 1, 2)"""
        )
        conn.execute(
            """INSERT INTO blocks(id, document_id, block_type, heading_path_json, ordinal,
                                  content, content_hash, start_line, end_line)
               VALUES('block-2', 'doc-2', 'paragraph', '[]', 0, '内容。', 'block-hash-2', 1, 2)"""
        )
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status, user_edited)
               VALUES('claim-1', '混合检索优于纯向量检索。', 'RAG', 'conclusion', 0.9, 'active', 0)"""
        )
        conn.execute(
            """INSERT INTO claims(id, statement, scope, claim_type, confidence, status, user_edited)
               VALUES('claim-2', '增大上下文窗口可能降低召回精度。', '', 'hypothesis', 0.7, 'active', 0)"""
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash, status)
               VALUES('evidence-1', 'claim-1', 'block-1', 'qh1', 'active')"""
        )
        conn.execute(
            """INSERT INTO evidence(id, claim_id, block_id, quote_hash, status)
               VALUES('evidence-2', 'claim-2', 'block-2', 'qh2', 'active')"""
        )
    yield semantic_store


def _claim(store: SemanticStore, claim_id: str) -> dict:
    return next(item for item in store.list_claims_for_verification(limit=100) if item["id"] == claim_id)


class TestParseVerificationJson:
    def test_bare_json(self) -> None:
        parsed = parse_verification_json(
            '{"verdict": "supported", "confidence": 0.8, "summary": "证据充分", "sources": []}'
        )
        assert parsed["verdict"] == "supported"
        assert parsed["confidence"] == 0.8
        assert parsed["summary"] == "证据充分"

    def test_fenced_json(self) -> None:
        parsed = parse_verification_json(
            '```json\n{"verdict": "refuted", "confidence": 0.6, "summary": "有反例", "sources": []}\n```'
        )
        assert parsed["verdict"] == "refuted"

    def test_embedded_in_agent_transcript(self) -> None:
        raw = (
            "我搜索了 3 轮，查看了官方文档。\n"
            '研究结论：{"verdict": "supported", "confidence": 0.9, "summary": "成立", '
            '"sources": [{"title": "文档", "url": "https://example.com/doc", "snippet": "关键片段"}]}\n'
            "以上为最终结论。"
        )
        parsed = parse_verification_json(raw)
        assert parsed["verdict"] == "supported"
        assert parsed["sources"][0]["url"] == "https://example.com/doc"
        assert parsed["sources"][0]["title"] == "文档"

    def test_invalid_verdict_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_verification_json('{"verdict": "yes", "confidence": 0.9}')

    def test_no_json_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_verification_json("没有任何 JSON 的研究报告")

    def test_sources_filtered_and_confidence_clamped(self) -> None:
        parsed = parse_verification_json(
            '{"verdict": "unclear", "confidence": 99, "summary": "x",'
            ' "sources": [{"url": "https://a.com"}, {"title": "无链接"}, "not-a-dict"]}'
        )
        assert parsed["confidence"] == 1.0
        assert len(parsed["sources"]) == 1


class TestStoreVerificationPersistence:
    def test_save_and_query(self, store: SemanticStore) -> None:
        saved = store.save_claim_verification(
            claim_id="claim-1",
            verdict="supported",
            confidence=0.85,
            summary="外部证据支持",
            method="web-search",
            sources=[{"title": "来源", "url": "https://example.com", "snippet": "片段"}],
        )
        assert saved is not None
        assert saved["verdict"] == "supported"

        latest = store.latest_claim_verification("claim-1")
        assert latest is not None
        assert latest["verdict"] == "supported"
        assert latest["sources"][0]["url"] == "https://example.com"

        history = store.claim_verifications("claim-1")
        assert len(history) == 1

    def test_save_unknown_claim_returns_none(self, store: SemanticStore) -> None:
        assert store.save_claim_verification(claim_id="nope", verdict="unclear", confidence=0.5) is None

    def test_invalid_verdict_rejected(self, store: SemanticStore) -> None:
        with pytest.raises(ValueError):
            store.save_claim_verification(claim_id="claim-1", verdict="maybe", confidence=0.5)

    def test_latest_verification_wins(self, store: SemanticStore) -> None:
        store.save_claim_verification(claim_id="claim-1", verdict="supported", confidence=0.8, summary="第一轮")
        store.save_claim_verification(claim_id="claim-1", verdict="refuted", confidence=0.7, summary="第二轮")
        latest = store.latest_claim_verification("claim-1")
        assert latest["verdict"] == "refuted"
        assert len(store.claim_verifications("claim-1")) == 2

    def test_list_filters_by_verified(self, store: SemanticStore) -> None:
        store.save_claim_verification(claim_id="claim-1", verdict="supported", confidence=0.8)
        unverified = store.list_claims_for_verification(verified=False)
        verified = store.list_claims_for_verification(verified=True)
        all_claims = store.list_claims_for_verification()
        assert [item["id"] for item in unverified] == ["claim-2"]
        assert [item["id"] for item in verified] == ["claim-1"]
        assert len(all_claims) == 2
        verified_claim = verified[0]
        assert verified_claim["verification"]["verdict"] == "supported"
        assert unverified[0]["verification"] is None

    def test_list_filters_by_topic(self, store: SemanticStore) -> None:
        items = store.list_claims_for_verification(topic="AI > RAG")
        assert [item["id"] for item in items] == ["claim-1"]
        assert store.list_claims_for_verification(topic="不存在的主题") == []


class TestVerifyClaimViaCli:
    def test_cli_verdict_saved(self, store: SemanticStore, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sidecar.semantic.claim_verifier.check_cli_agent",
            lambda agent_id: (True, ""),
        )
        monkeypatch.setattr(
            "sidecar.cli_agent.registry.run_cli_agent",
            lambda agent_id, prompt, send_event=None: {
                "success": True,
                "message": "",
                "output": (
                    "已核查 5 个来源。\n"
                    '```json\n{"verdict": "refuted", "confidence": 0.75, "summary": "存在可靠反例",'
                    ' "sources": [{"title": "B", "url": "https://b.com", "snippet": "反例"}]}\n```'
                ),
            },
        )
        result = verify_claim_via_cli(store, _claim(store, "claim-1"), agent_id="claude")
        assert result["success"] is True
        verification = result["verification"]
        assert verification["verdict"] == "refuted"
        assert verification["method"] == "cli"
        assert verification["agent"] == "claude"
        assert store.latest_claim_verification("claim-1")["verdict"] == "refuted"

    def test_cli_failure_not_saved(self, store: SemanticStore, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sidecar.semantic.claim_verifier.check_cli_agent",
            lambda agent_id: (True, ""),
        )
        monkeypatch.setattr(
            "sidecar.cli_agent.registry.run_cli_agent",
            lambda agent_id, prompt, send_event=None: {
                "success": False,
                "message": "claude 未安装",
                "output": "",
            },
        )
        result = verify_claim_via_cli(store, _claim(store, "claim-1"), agent_id="claude")
        assert result["success"] is False
        assert store.latest_claim_verification("claim-1") is None

    def test_cli_unparseable_output_not_saved(self, store: SemanticStore, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sidecar.semantic.claim_verifier.check_cli_agent",
            lambda agent_id: (True, ""),
        )
        monkeypatch.setattr(
            "sidecar.cli_agent.registry.run_cli_agent",
            lambda agent_id, prompt, send_event=None: {"success": True, "message": "", "output": "研究完毕，无结构化输出"},
        )
        result = verify_claim_via_cli(store, _claim(store, "claim-1"), agent_id="claude")
        assert result["success"] is False
        assert "无法解析" in result["message"]
        assert store.latest_claim_verification("claim-1") is None

    def test_cli_agent_missing_key(self, store: SemanticStore, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "sidecar.semantic.claim_verifier.check_cli_agent",
            lambda agent_id: (False, "缺少 API key"),
        )
        result = verify_claim_via_cli(store, _claim(store, "claim-1"), agent_id="claude")
        assert result["success"] is False
        assert "API key" in result["message"]


class TestPromptBuilder:
    def test_cli_prompt_contains_statement_scope_and_contract(self) -> None:
        prompt = build_cli_research_prompt(
            {"statement": "混合检索优于纯向量检索。", "scope": "RAG"},
            context="Notes/AI.md",
        )
        assert "混合检索优于纯向量检索。" in prompt
        assert "RAG" in prompt
        assert "Notes/AI.md" in prompt
        assert '"verdict"' in prompt
        assert '"sources"' in prompt


class TestHandlerAttachesVerification:
    @pytest.fixture
    def handler(self, store: SemanticStore):
        previous = config.workspace_path
        config.workspace_path = str(store.workspace)
        yield SemanticHandler(SimpleNamespace(_ctx=SimpleNamespace(config=config, logger=None)))
        config.workspace_path = previous

    def test_claim_list_and_detail_carry_verification(self, handler: SemanticHandler) -> None:
        handler._store().save_claim_verification(
            claim_id="claim-1",
            verdict="supported",
            confidence=0.8,
            summary="外部证据支持",
            method="web-search",
        )
        listing = handler._get_workbench({"tab": "claims"})
        item = next(value for value in listing["items"] if value["id"] == "claim-1")
        assert item["verification"] == {
            "verdict": "supported",
            "confidence": 0.8,
            "method": "web-search",
            "agent": "",
            "verified_at": item["verification"]["verified_at"],
        }
        detail = handler._get_detail({"kind": "claim", "id": "claim-1"})
        assert detail["item"]["verifications"][0]["verdict"] == "supported"
        assert detail["item"]["verifications"][0]["sources"] == []

    def test_unverified_claim_has_null_verification(self, handler: SemanticHandler) -> None:
        listing = handler._get_workbench({"tab": "claims"})
        item = next(value for value in listing["items"] if value["id"] == "claim-2")
        assert item["verification"] is None
        assert json.loads(json.dumps(item, ensure_ascii=False))  # JSON-serializable
