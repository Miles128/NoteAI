from __future__ import annotations

import sqlite3
from pathlib import Path

from sidecar.semantic.compiler import compile_note_semantics, compile_semantic_batch
from sidecar.semantic.extractor import (
    ExtractionValidationError,
    extract_document_semantics,
    parse_extraction_json,
    validate_extraction,
)
from sidecar.semantic.parser import parse_semantic_blocks
from sidecar.semantic.store import SemanticStore
from sidecar.semantic.topic_state import build_topic_state, materialize_topic_state


def _note(workspace: Path, content: str) -> Path:
    path = workspace / "Notes" / "RAG" / "测试.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_parser_keeps_unmodified_block_ids_stable():
    original = "# 标题\n\n## 第一节\n\n第一段。\n\n第二段。\n"
    changed = "# 标题\n\n## 第一节\n\n新增段落。\n\n第一段。\n\n第二段。\n"

    before = parse_semantic_blocks("doc_test", original)
    after = parse_semantic_blocks("doc_test", changed)

    before_ids = {block.content: block.id for block in before}
    after_ids = {block.content: block.id for block in after}
    assert before_ids["第一段。"] == after_ids["第一段。"]
    assert before_ids["第二段。"] == after_ids["第二段。"]


def test_parser_preserves_source_line_locations_with_frontmatter():
    markdown = "---\ntopic: RAG\n---\n\n## 检索\n\n证据段落。\n"
    blocks = parse_semantic_blocks("doc_test", markdown)
    assert len(blocks) == 1
    assert blocks[0].heading_path == ("检索",)
    assert blocks[0].start_line == 7
    assert blocks[0].end_line == 7


def test_compile_is_idempotent_and_persists_blocks(tmp_path: Path):
    note = _note(
        tmp_path,
        "---\ntitle: 测试\ntopic: RAG > 检索\ntags: [RAG, 检索]\n---\n\n## 定义\n\n混合检索结合不同检索信号。\n",
    )

    first = compile_note_semantics(tmp_path, note)
    second = compile_note_semantics(tmp_path, note)

    assert first["success"] is True
    assert first["skipped"] is False
    assert first["blocks"] == 1
    assert second["skipped"] is True
    assert second["document_id"] == first["document_id"]

    store = SemanticStore(tmp_path)
    rows = store.blocks_for_document(first["document_id"])
    assert len(rows) == 1
    assert rows[0]["content"] == "混合检索结合不同检索信号。"
    assert (tmp_path / ".noteai" / "compiler" / "manifest.json").exists()


def test_batch_snapshots_all_documents_before_extraction(tmp_path: Path, monkeypatch):
    first = _note(tmp_path, "## 第一篇\n\n证据一。\n")
    second = tmp_path / "Notes" / "RAG" / "第二篇.md"
    second.write_text("## 第二篇\n\n证据二。\n", encoding="utf-8")
    observed_document_counts: list[int] = []

    def fake_extract(store: SemanticStore, _document_id: str):
        with store.connect() as conn:
            observed_document_counts.append(conn.execute("SELECT count(*) FROM documents").fetchone()[0])
        return {"extracted": 0, "claims": 0, "failed": 0, "pending": False, "failures": []}

    monkeypatch.setattr("sidecar.semantic.extractor.extract_document_semantics", fake_extract)
    result = compile_semantic_batch(tmp_path, [first, second])

    assert result["documents"] == 2
    assert observed_document_counts == [2, 2]


def test_compile_replaces_only_changed_blocks(tmp_path: Path):
    note = _note(tmp_path, "## 章节\n\n保留。\n\n旧内容。\n")
    first = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    old = {row["content"]: row["id"] for row in store.blocks_for_document(first["document_id"])}

    note.write_text("## 章节\n\n保留。\n\n新内容。\n", encoding="utf-8")
    second = compile_note_semantics(tmp_path, note)
    new = {row["content"]: row["id"] for row in store.blocks_for_document(second["document_id"])}

    assert old["保留。"] == new["保留。"]
    assert "旧内容。" not in new
    assert "新内容。" in new


def test_store_rolls_back_document_replace_on_failure(tmp_path: Path):
    note = _note(tmp_path, "## 章节\n\n原内容。\n")
    result = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)

    with store.connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0]

    try:
        with store.connect() as conn:
            conn.execute("DELETE FROM blocks")
            conn.execute("INSERT INTO missing_table VALUES (1)")
    except sqlite3.OperationalError:
        pass

    assert len(store.blocks_for_document(result["document_id"])) == before


def test_validation_rejects_claim_without_exact_evidence():
    data = {
        "concepts": [],
        "entities": [],
        "claims": [
            {
                "statement": "混合检索更好",
                "scope": "",
                "confidence": 0.8,
                "evidence_quote": "原文中不存在的句子",
            }
        ],
    }
    try:
        validate_extraction(data, block_id="blk_test", block_content="混合检索结合两种信号。")
    except ExtractionValidationError as exc:
        assert "不是当前块" in str(exc)
    else:
        raise AssertionError("expected evidence validation failure")


def test_extractor_persists_only_evidence_backed_claims(tmp_path: Path):
    note = _note(tmp_path, "## 定义\n\n混合检索结合向量检索与关键词检索。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)

    def fake_llm(_prompt: str) -> str:
        return """{
          "concepts": [{"name": "混合检索", "description": "组合检索信号", "confidence": 0.9}],
          "entities": [],
          "claims": [{
            "statement": "混合检索结合向量检索与关键词检索",
            "scope": "检索系统",
            "confidence": 0.95,
            "evidence_quote": "混合检索结合向量检索与关键词检索。"
          }]
        }"""

    result = extract_document_semantics(store, compiled["document_id"], llm_call=fake_llm)
    assert result["success"] is True
    assert result["extracted"] == 1
    assert result["claims"] == 1

    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1

    repeated = extract_document_semantics(store, compiled["document_id"], llm_call=fake_llm)
    assert repeated["extracted"] == 0
    assert repeated["skipped"] == 1


def test_extractor_records_invalid_json_as_partial(tmp_path: Path):
    note = _note(tmp_path, "## 定义\n\n正文。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)

    result = extract_document_semantics(store, compiled["document_id"], llm_call=lambda _: "not json")
    assert result["success"] is False
    assert result["failed"] == 1
    assert "合法 JSON" in result["failures"][0]["error"]
    assert store.document("Notes/RAG/测试.md")["status"] == "partial"


def test_extractor_repairs_invalid_output_once(tmp_path: Path):
    note = _note(tmp_path, "## 定义\n\n可追溯证据。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    responses = iter(
        [
            "not json",
            '{"concepts": [], "entities": [], "claims": [{"statement": "存在证据", "scope": "", "confidence": 0.8, "evidence_quote": "可追溯证据。"}]}',
        ]
    )

    result = extract_document_semantics(store, compiled["document_id"], llm_call=lambda _: next(responses))
    assert result["success"] is True
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1


def test_extractor_records_llm_timeout_without_writing_facts(tmp_path: Path):
    note = _note(tmp_path, "## 定义\n\n正文。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)

    def timeout(_prompt: str) -> str:
        raise RuntimeError("LLM 调用超时（90秒）")

    result = extract_document_semantics(store, compiled["document_id"], llm_call=timeout)
    assert result["failed"] == 1
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0


def test_default_extractor_batches_multiple_blocks(tmp_path: Path, monkeypatch):
    note = _note(tmp_path, "## 第一节\n\n证据一。\n\n## 第二节\n\n证据二。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    blocks = store.blocks_for_document(compiled["document_id"])
    calls: list[str] = []

    monkeypatch.setattr("utils.llm_utils.check_api_config", lambda: (True, ""))

    def fake_call(prompt: str, **_kwargs):
        calls.append(prompt)
        return f'''{{
          "blocks": [
            {{"block_id": "{blocks[0]['id']}", "concepts": [], "entities": [],
              "claims": [{{"statement": "第一条", "scope": "", "confidence": 0.9, "evidence_quote": "证据一。"}}]}},
            {{"block_id": "{blocks[1]['id']}", "concepts": [], "entities": [],
              "claims": [{{"statement": "第二条", "scope": "", "confidence": 0.9, "evidence_quote": "证据二。"}}]}}
          ]
        }}'''

    monkeypatch.setattr("utils.llm_utils.call_llm_raw", fake_call)
    result = extract_document_semantics(store, compiled["document_id"])

    assert result["extracted"] == 2
    assert result["claims"] == 2
    assert len(calls) == 1


def test_extractor_discards_result_when_source_changes_during_call(tmp_path: Path):
    note = _note(tmp_path, "## 定义\n\n旧证据。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)

    def mutate_source(_prompt: str) -> str:
        note.write_text("## 定义\n\n新证据。\n", encoding="utf-8")
        return '{"concepts": [], "entities": [], "claims": [{"statement": "旧命题", "scope": "", "confidence": 0.8, "evidence_quote": "旧证据。"}]}'

    result = extract_document_semantics(store, compiled["document_id"], llm_call=mutate_source)
    assert result["failed"] == 1
    assert "发生变化" in result["failures"][0]["error"]
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0


def test_parse_extraction_json_accepts_json_fence():
    parsed = parse_extraction_json('```json\n{"concepts": [], "entities": [], "claims": []}\n```')
    assert parsed["claims"] == []


def test_topic_state_contains_traceable_claim_evidence(tmp_path: Path):
    note = _note(
        tmp_path,
        "---\ntopic: RAG > 检索\n---\n\n## 定义\n\n混合检索结合向量检索与关键词检索。\n",
    )
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    extract_document_semantics(
        store,
        compiled["document_id"],
        llm_call=lambda _: """{
          "concepts": [], "entities": [],
          "claims": [{
            "statement": "混合检索结合两类检索信号",
            "scope": "RAG",
            "confidence": 0.9,
            "evidence_quote": "混合检索结合向量检索与关键词检索。"
          }]
        }""",
    )

    state = build_topic_state(store, "RAG > 检索")
    assert state["stats"] == {"documents": 1, "claims": 1}
    evidence = state["claims"][0]["evidence"][0]
    assert evidence["document_path"] == "Notes/RAG/测试.md"
    assert evidence["heading_path"] == ["定义"]
    assert evidence["start_line"] == 7

    path = materialize_topic_state(store, "RAG > 检索")
    assert path.exists()
    assert path.parent.name == "topic_states"


def test_deleting_source_purges_evidence_and_orphan_claim(tmp_path: Path):
    note = _note(tmp_path, "---\ntopic: RAG\n---\n\n正文证据。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    extract_document_semantics(
        store,
        compiled["document_id"],
        llm_call=lambda _: """{
          "concepts": [], "entities": [],
          "claims": [{
            "statement": "存在正文证据", "scope": "", "confidence": 0.9,
            "evidence_quote": "正文证据。"
          }]
        }""",
    )
    note.unlink()

    topics = store.purge_missing_documents()
    assert topics == ["RAG"]
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
