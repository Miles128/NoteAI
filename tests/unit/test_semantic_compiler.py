from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sidecar.semantic.compiler import compile_note_semantics, compile_semantic_batch
from sidecar.semantic.extractor import (
    _QUOTE_PUNCT_RE,
    ExtractionValidationError,
    _quote_matches,
    build_batch_extraction_prompt,
    build_extraction_prompt,
    extract_document_semantics,
    parse_extraction_json,
    validate_extraction,
)
from sidecar.semantic.ids import stable_id
from sidecar.semantic.parser import parse_semantic_blocks
from sidecar.semantic.store import CLAIM_POLICY_VERSION, SemanticStore, name_fingerprint
from sidecar.semantic.topic_state import build_topic_state, materialize_topic_state
from sidecar.semantic.wiki import build_topic_wiki_page, materialize_topic_wiki_page


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

    def fake_extract(store: SemanticStore, _document_id: str, **_kwargs):
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


def test_validation_drops_claim_without_exact_evidence_but_keeps_valid_block_output():
    data = {
        "concepts": [{"name": "混合检索", "description": "组合信号", "confidence": 0.8}],
        "entities": [],
        "claims": [
            {
                "statement": "混合检索更好",
                "claim_type": "conclusion",
                "scope": "",
                "confidence": 0.8,
                "evidence_quote": "原文中不存在的句子",
            },
            {
                "statement": "混合检索比单一检索更稳健",
                "claim_type": "conclusion",
                "scope": "检索系统",
                "confidence": 0.9,
                "evidence_quote": "混合检索结合两种信号。",
            },
        ],
    }
    parsed = validate_extraction(data, block_id="blk_test", block_content="混合检索结合两种信号。")
    assert [item["canonical_name"] for item in parsed["concepts"]] == ["混合检索"]
    assert [item["statement"] for item in parsed["claims"]] == ["混合检索比单一检索更稳健"]


def test_quote_matches_accepts_ellipsis_segments_in_order():
    """引文以省略号拼接多个片段时，片段按序存在于原文即接受。"""
    block = "混合检索结合两种信号，排序后返回结果。"
    ok = _quote_matches("混合检索结合……返回结果", block)
    assert ok
    # 顺序颠倒的片段不应接受
    assert not _quote_matches("返回结果……混合检索结合", block)


def test_quote_matches_accepts_minor_character_differences():
    """去标点后与原文相似度 ≥0.90 的引文（个别字差异）可接受。"""
    block = "混合检索结合两种信号，排序后返回结果"
    compact = _QUOTE_PUNCT_RE.sub("", block)
    # 把“结合”改为“组合”（1 字差异，长度 14 时相似度 > 0.9）
    assert _quote_matches("混合检索组合两种信号排序后返回结果", block)
    assert len(_QUOTE_PUNCT_RE.sub("", "混合检索组合两种信号排序后返回结果")) == len(compact)


def test_quote_matches_rejects_unrelated_or_too_short_quotes():
    """完全无关或过短的引文仍被拒绝，不因放宽而放行噪声。"""
    block = "混合检索结合两种信号，排序后返回结果"
    assert not _quote_matches("完全无关的句子内容", block)
    # 过短（<8 紧凑字符）且不匹配
    assert not _quote_matches("混合搜", block)


def test_validation_drops_facts_instructions_and_missing_claim_type():

    for claim_type in (None, "fact", "instruction", "description"):
        item = {
            "statement": "--port 参数指定服务端口",
            "scope": "CLI",
            "confidence": 0.9,
            "evidence_quote": "--port 参数指定服务端口。",
        }
        if claim_type is not None:
            item["claim_type"] = claim_type
        parsed = validate_extraction(
            {"concepts": [], "entities": [], "claims": [item]},
            block_id="blk_instruction",
            block_content="--port 参数指定服务端口。",
        )
        assert parsed["claims"] == []


def test_validation_drops_plain_numeric_and_product_attributes_mislabeled_as_claims():
    for statement, source in (
        ("75+ 模型", "75+ 模型"),
        ("该产品支持 75 种模型", "该产品支持 75 种模型。"),
        ("Python 3.10 发布于 2021 年", "Python 3.10 发布于 2021 年。"),
    ):
        parsed = validate_extraction(
            {
                "concepts": [],
                "entities": [],
                "claims": [
                    {
                        "statement": statement,
                        "claim_type": "conclusion",
                        "scope": "",
                        "confidence": 0.95,
                        "evidence_quote": source,
                    }
                ],
            },
            block_id="blk_plain_fact",
            block_content=source,
        )
        assert parsed["claims"] == []


def test_validation_keeps_quantitative_comparisons_and_explicit_hypotheses():
    source = "实验显示新方案的准确率比基线高 20%。该方案可能降低长文本召回率。"
    parsed = validate_extraction(
        {
            "concepts": [],
            "entities": [],
            "claims": [
                {
                    "statement": "新方案的准确率比基线高 20%",
                    "claim_type": "conclusion",
                    "scope": "该实验",
                    "confidence": 0.9,
                    "evidence_quote": "实验显示新方案的准确率比基线高 20%。",
                },
                {
                    "statement": "该方案可能降低长文本召回率",
                    "claim_type": "hypothesis",
                    "scope": "长文本",
                    "confidence": 0.8,
                    "evidence_quote": "该方案可能降低长文本召回率。",
                },
            ],
        },
        block_id="blk_research_claims",
        block_content=source,
    )
    assert [item["claim_type"] for item in parsed["claims"]] == ["conclusion", "hypothesis"]


def test_validation_drops_claim_from_code_block_but_keeps_entities():
    data = {
        "concepts": [],
        "entities": [{"name": "uv", "type": "product", "description": "", "confidence": 0.8}],
        "claims": [
            {
                "statement": "该命令更适合生产环境",
                "claim_type": "conclusion",
                "scope": "部署",
                "confidence": 0.8,
                "evidence_quote": "uv run app.py",
            }
        ],
    }
    parsed = validate_extraction(
        data,
        block_id="blk_code",
        block_content="```bash\nuv run app.py\n```",
        block_type="code",
    )
    assert parsed["claims"] == []
    assert [item["canonical_name"] for item in parsed["entities"]] == ["uv"]


def test_validation_still_rejects_malformed_claim_collection():
    try:
        validate_extraction(
            {"concepts": [], "entities": [], "claims": {}},
            block_id="blk_invalid_schema",
            block_content="正文。",
        )
    except ExtractionValidationError as exc:
        assert "claims 必须是数组" in str(exc)
    else:
        raise AssertionError("expected malformed claims collection to fail validation")


def test_claim_prompt_excludes_facts_and_command_documentation():
    prompt = build_extraction_prompt(
        block_id="blk_test",
        heading_path="CLI",
        content="--port 参数指定服务端口。",
    )
    assert '"claim_type": "conclusion|hypothesis"' in prompt
    assert "命令/参数/API/配置说明" in prompt
    assert "75+ 模型" in prompt
    assert "不是 Claim" in prompt


def test_extraction_prompt_embeds_noise_gate_and_variant_dedup_rules():
    """门禁与查重规则必须在 LLM 生成之前出现在 prompt 里。"""
    prompt = build_extraction_prompt(
        block_id="blk_test",
        heading_path="检索",
        content="RAG（检索增强生成）结合向量与关键词。",
    )
    # 变体查重：括号注释与变体写法不能输出
    assert "「RAG（检索增强生成）」「可灵(Kling)」应输出为「RAG」「可灵」" in prompt
    assert "同一对象只输出一次" in prompt
    assert "名称内不夹空格" in prompt
    # 噪声门禁：标题词、@引用、全大写下划线、量纲
    assert "报告、指南、路线图、全景" in prompt
    assert "@file、@tool" in prompt
    assert "AGENT_TRIGGERS" in prompt
    assert "200K token" in prompt

    batch = build_batch_extraction_prompt(
        [
            {
                "id": "b1",
                "hash": "h1",
                "type": "paragraph",
                "heading": "检索",
                "content": "GraphRAG 与 RAG 对比。",
            }
        ]
    )
    assert "同一对象只输出一次" in batch
    assert "@file、@tool" in batch


def test_name_fingerprint_stems_english_plurals():
    """英文复数变体（Skill/Skills、Token/Tokens）必须解析为同一指纹。"""
    from sidecar.semantic.store import name_fingerprint

    assert name_fingerprint("Skill") == name_fingerprint("Skills")
    assert name_fingerprint("Token") == name_fingerprint("Tokens")
    assert name_fingerprint("Model") == name_fingerprint("Models")
    assert name_fingerprint("Query") == name_fingerprint("Queries")
    assert name_fingerprint("Box") == name_fingerprint("Boxes")
    assert name_fingerprint("Process") == name_fingerprint("Processes")
    # 与既有能力保持兼容：括号注释、大小写、空白
    assert name_fingerprint("RAG（检索增强生成）") == name_fingerprint("RAG")
    assert name_fingerprint("R A G") == name_fingerprint("RAG")
    assert name_fingerprint("large language models") == name_fingerprint("Large Language Model")


def test_name_fingerprint_keeps_plural_like_proper_nouns():
    """ss/us/is/os/as 结尾的词（class/status/analysis/alias）不能被误砍。"""
    from sidecar.semantic.store import name_fingerprint

    assert name_fingerprint("Class") != name_fingerprint("Cla")
    assert name_fingerprint("Status") != name_fingerprint("Statu")
    assert name_fingerprint("Analysis") != name_fingerprint("Analys")
    assert name_fingerprint("Alias") != name_fingerprint("Alia")
    # 非纯字母（数字、连字符）与短词不参与词干化
    assert name_fingerprint("GPT-4") == "gpt4"
    assert name_fingerprint("RAG") == "rag"


def test_name_fingerprint_collapses_punctuation_variants():
    """标点变体（连字符/中点/书名号/顿号）必须解析为同一指纹。"""
    from sidecar.semantic.store import name_fingerprint

    assert name_fingerprint("DALL-E") == name_fingerprint("DALL·E") == "dalle"
    assert name_fingerprint("DeepSeek V3") == name_fingerprint("DeepSeek-V3") == "deepseekv3"
    assert name_fingerprint("GPT2") == name_fingerprint("GPT-2") == "gpt2"
    assert name_fingerprint("感知机") == name_fingerprint("《感知机》")
    assert name_fingerprint("D2L.ai 动手学深度学习") == name_fingerprint("D2L.ai，动手学深度学习")
    assert name_fingerprint("M×N 个适配器") == name_fingerprint("M+N 个适配器")
    # 符号型短名（C++/C#）不能被剥成单字母而与单字母名误并
    assert name_fingerprint("C++") == "c++" and name_fingerprint("C") == "c"
    assert name_fingerprint("C++") != name_fingerprint("C")
    assert name_fingerprint("C#") != name_fingerprint("C")


def test_extraction_dedups_variant_spellings_into_existing_object(tmp_path: Path):
    """抽取落库时，变体写法（复数/括号/大小写）合并到既有 active 对象。"""
    note = _note(tmp_path, "## 定义\n\nSkill 与 Token 是 AI 的核心概念。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    now = "2026-07-17T10:00:00Z"
    with store.connect() as conn:
        block = conn.execute("SELECT id, content_hash FROM blocks LIMIT 1").fetchone()
    block_id, block_hash = block["id"], block["content_hash"]

    def _claim():
        return []

    def _save(concept_name: str, entity_name: str) -> str:
        concept_id = stable_id("con", concept_name.casefold())
        entity_id = stable_id("ent", entity_name.casefold())
        store.save_block_extraction(
            block_id=block_id,
            block_hash=block_hash,
            prompt_version=4,
            extracted_at=now,
            concepts=[
                {
                    "id": concept_id,
                    "canonical_name": concept_name,
                    "description": "能力",
                    "confidence": 0.9,
                }
            ],
            entities=[
                {
                    "id": entity_id,
                    "canonical_name": entity_name,
                    "entity_type": "concept_type",
                    "description": "单元",
                    "confidence": 0.8,
                }
            ],
            claims=_claim(),
        )
        with store.connect() as conn:
            return conn.execute(
                "SELECT id FROM concepts WHERE name_fingerprint = ?", (name_fingerprint(concept_name),)
            ).fetchone()["id"]

    first_id = _save("Skills", "Token")
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM concepts WHERE status = 'active'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM entities WHERE status = 'active'").fetchone()[0] == 1

    # 变体写法（Skill / Tokens）必须合并进既有对象而非新建行
    merged_id = _save("Skill", "Tokens")
    assert merged_id == first_id
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM concepts WHERE status = 'active'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM entities WHERE status = 'active'").fetchone()[0] == 1
        concept = conn.execute("SELECT canonical_name FROM concepts WHERE status = 'active'").fetchone()
        assert concept["canonical_name"] == "Skills"  # 保留首个规范名
        concept = conn.execute("SELECT id FROM concepts WHERE status = 'active'").fetchone()
        assert concept["id"] == first_id


def test_merge_duplicate_entities_collapses_english_plural_variants(tmp_path: Path):
    """编译期 merge 阶段把历史 Skill/Skills 复数变体合并为一行。"""
    store = SemanticStore(tmp_path)
    store.initialize()
    with store.connect() as conn:
        for name in ("Skill", "Skills", "Token", "Tokens"):
            conn.execute(
                """INSERT INTO concepts(id, canonical_name, description, confidence, status, name_fingerprint)
                   VALUES(?, ?, '描述', 0.8, 'active', ?)""",
                ("concept-" + name.lower(), name, name),
            )
    store.initialize()  # 触发指纹算法版本重算
    stats = store.merge_duplicate_entities()
    assert stats["merged_concepts"] == 2
    with store.connect() as conn:
        active = [
            row["canonical_name"] for row in conn.execute("SELECT canonical_name FROM concepts WHERE status = 'active'")
        ]
        assert sorted(active) == ["Skill", "Token"]


def test_merge_duplicate_entities_collapses_punctuation_variants_and_records_alias(tmp_path: Path):
    """编译期 merge 把 DALL-E/DALL·E 类标点变体合并，并把变体名记入别名。"""
    store = SemanticStore(tmp_path)
    store.initialize()
    with store.connect() as conn:
        for idx, (name, table, kind, confidence) in enumerate(
            (
                ("DALL-E", "entities", "entity", 0.9),
                ("DALL·E", "entities", "entity", 0.8),
                ("感知机", "concepts", "concept", 0.9),
                ("《感知机》", "concepts", "concept", 0.8),
            )
        ):
            if table == "entities":
                conn.execute(
                    """INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status, name_fingerprint)
                       VALUES(?, ?, 'product', '描述', ?, 'active', '')""",
                    (f"entity-{idx}", name, confidence),
                )
            else:
                conn.execute(
                    """INSERT INTO concepts(id, canonical_name, description, confidence, status, name_fingerprint)
                       VALUES(?, ?, '描述', ?, 'active', '')""",
                    (f"concept-{idx}", name, confidence),
                )
    stats = store.merge_duplicate_entities()
    assert stats["merged_entities"] == 1
    assert stats["merged_concepts"] == 1
    with store.connect() as conn:
        entity = conn.execute("SELECT * FROM entities WHERE status = 'active'").fetchone()
        assert entity["canonical_name"] == "DALL-E"
        aliases = [
            row["alias"] for row in conn.execute("SELECT alias FROM entity_aliases WHERE entity_id = ?", (entity["id"],))
        ]
        assert "DALL·E" in aliases
        concept = conn.execute("SELECT * FROM concepts WHERE status = 'active'").fetchone()
        assert concept["canonical_name"] == "感知机"
        concept_aliases = [
            row["alias"]
            for row in conn.execute("SELECT alias FROM concept_aliases WHERE concept_id = ?", (concept["id"],))
        ]
        assert "《感知机》" in concept_aliases


def test_merge_duplicate_entities_transfers_aliases_and_dedups_relations(tmp_path: Path):
    """merge 时 dup 的存量别名转移到 keeper，同键关系去重保留高置信度。"""
    store = SemanticStore(tmp_path)
    store.initialize()
    with store.connect() as conn:
        conn.execute(
            """INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status, name_fingerprint)
               VALUES('e-1', 'LLM', 'model', 'd', 0.95, 'active', '')"""
        )
        conn.execute(
            """INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status, name_fingerprint)
               VALUES('e-2', 'LLM（大语言模型）', 'model', 'd', 0.8, 'active', '')"""
        )
        conn.execute("INSERT INTO entity_aliases(alias, entity_id, created_at) VALUES('大语言模型', 'e-2', '2026-01-01')")
        conn.execute(
            "INSERT INTO relations(id, source_id, relation_type, target_id, confidence, evidence_id, block_id)"
            " VALUES('r-1', 'e-1', 'RELATED_TO', 'x', 0.6, NULL, NULL)"
        )
        conn.execute(
            "INSERT INTO relations(id, source_id, relation_type, target_id, confidence, evidence_id, block_id)"
            " VALUES('r-2', 'e-2', 'RELATED_TO', 'x', 0.9, NULL, NULL)"
        )
    store.merge_duplicate_entities()
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 1
        relation = conn.execute("SELECT * FROM relations").fetchone()
        assert relation["source_id"] == "e-1"
        assert relation["confidence"] == 0.9
        aliases = {
            row["alias"] for row in conn.execute("SELECT alias FROM entity_aliases WHERE entity_id = 'e-1'")
        }
        assert "大语言模型" in aliases  # dup 的存量别名转移
        assert "LLM（大语言模型）" in aliases  # dup 的变体规范名入别名


def test_extraction_time_variant_spelling_records_alias(tmp_path: Path):
    """抽取落库时，变体写法复用既有对象并把不同名称记入别名（实体+概念）。"""
    note = _note(tmp_path, "## 定义\n\nDALL-E 与 M×N 适配器是常见概念。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    with store.connect() as conn:
        block = conn.execute("SELECT id, content_hash FROM blocks LIMIT 1").fetchone()
    block_id, block_hash = block["id"], block["content_hash"]

    def _save(entity_name: str, concept_name: str) -> tuple[str, str]:
        store.save_block_extraction(
            block_id=block_id,
            block_hash=block_hash,
            prompt_version=4,
            extracted_at="2026-07-17T10:00:00Z",
            concepts=[
                {
                    "id": stable_id("con", concept_name.casefold()),
                    "canonical_name": concept_name,
                    "description": "能力",
                    "confidence": 0.9,
                }
            ],
            entities=[
                {
                    "id": stable_id("ent", entity_name.casefold()),
                    "canonical_name": entity_name,
                    "entity_type": "product",
                    "description": "模型",
                    "confidence": 0.8,
                }
            ],
            claims=[],
        )
        with store.connect() as conn:
            entity = conn.execute("SELECT id, canonical_name FROM entities WHERE status = 'active'").fetchone()
            concept = conn.execute("SELECT id, canonical_name FROM concepts WHERE status = 'active'").fetchone()
        return entity["id"], concept["id"]

    first = _save("DALL-E", "M+N 个适配器")
    second = _save("DALL·E", "M×N 个适配器")
    assert second == first  # 变体复用同一 id，未新建行
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM entities WHERE status = 'active'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM concepts WHERE status = 'active'").fetchone()[0] == 1
        entity_aliases = [
            row["alias"] for row in conn.execute("SELECT alias FROM entity_aliases")
        ]
        concept_aliases = [
            row["alias"] for row in conn.execute("SELECT alias FROM concept_aliases")
        ]
        assert "DALL·E" in entity_aliases
        assert "M×N 个适配器" in concept_aliases


def test_extraction_time_cross_kind_reuses_existing_object(tmp_path: Path):
    """抽取时概念命中既有实体（或反之）→ 沿用先出现的 kind 复用 id，不双表并存。"""
    note = _note(tmp_path, "## 定义\n\nMCP 与 RAG 是常见的 AI 概念。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    with store.connect() as conn:
        block = conn.execute("SELECT id, content_hash FROM blocks LIMIT 1").fetchone()
    block_id, block_hash = block["id"], block["content_hash"]

    def _save(concept_name: str | None, entity_name: str | None) -> None:
        store.save_block_extraction(
            block_id=block_id,
            block_hash=block_hash,
            prompt_version=4,
            extracted_at="2026-07-17T10:00:00Z",
            concepts=(
                [
                    {
                        "id": stable_id("con", concept_name.casefold()),
                        "canonical_name": concept_name,
                        "description": "定义",
                        "confidence": 0.9,
                    }
                ]
                if concept_name
                else []
            ),
            entities=(
                [
                    {
                        "id": stable_id("ent", entity_name.casefold()),
                        "canonical_name": entity_name,
                        "entity_type": "protocol",
                        "description": "协议",
                        "confidence": 0.8,
                    }
                ]
                if entity_name
                else []
            ),
            claims=[],
        )

    # 先建立实体 MCP，随后抽取概念 MCP（模型上下文协议）应复用实体
    _save(None, "MCP")
    with store.connect() as conn:
        entity = conn.execute("SELECT id, canonical_name FROM entities WHERE status = 'active'").fetchone()
        assert entity["canonical_name"] == "MCP"
        entity_id = entity["id"]
    _save("MCP（模型上下文协议）", None)
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM entities WHERE status = 'active'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM concepts WHERE status = 'active'").fetchone()[0] == 0
        # 该 block 的 mentions 被重建为 1 条，且挂到既有实体而非新建概念
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM semantic_mentions WHERE object_id = ? AND object_kind = 'entity'",
                (entity_id,),
            ).fetchone()[0]
            == 1
        )
        aliases = [row["alias"] for row in conn.execute("SELECT alias FROM entity_aliases")]
        assert "MCP（模型上下文协议）" in aliases

    # 反向：先建立概念 RAG，随后抽取实体 RAG 应复用概念
    _save("RAG", None)
    with store.connect() as conn:
        concept = conn.execute("SELECT id, canonical_name FROM concepts WHERE status = 'active'").fetchone()
        assert concept["canonical_name"] == "RAG"
        concept_id = concept["id"]
    _save(None, "RAG")
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM concepts WHERE status = 'active'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM entities WHERE status = 'active'").fetchone()[0] == 1  # 仍只有 MCP
        mentions = conn.execute(
            "SELECT COUNT(*) FROM semantic_mentions WHERE object_id = ? AND object_kind = 'concept'",
            (concept_id,),
        ).fetchone()[0]
        assert mentions == 1


def test_extractor_persists_only_evidence_backed_claims(tmp_path: Path):
    note = _note(tmp_path, "## 定义\n\n混合检索结合向量检索与关键词检索。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)

    def fake_llm(_prompt: str) -> str:
        return """{
          "concepts": [{"name": "混合检索", "description": "组合检索信号", "confidence": 0.9}],
          "entities": [],
          "claims": [{
            "statement": "混合检索比单一检索更稳健",
            "claim_type": "conclusion",
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
        claim = conn.execute("SELECT claim_type FROM claims").fetchone()
        assert claim["claim_type"] == "conclusion"
        assert conn.execute("SELECT COUNT(*) FROM claim_extractions").fetchone()[0] == 1

    repeated = extract_document_semantics(store, compiled["document_id"], llm_call=fake_llm)
    assert repeated["extracted"] == 0
    assert repeated["skipped"] == 1


def test_claim_only_compile_preserves_concepts_entities_and_full_extraction_state(tmp_path: Path):
    note = _note(tmp_path, "## 判断\n\n该方案在当前数据集上更稳健。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    block = store.blocks_for_document(compiled["document_id"])[0]
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO concepts(id, canonical_name, description, confidence, status)"
            " VALUES('concept-keep', '保留概念', '不应变化', 0.8, 'active')"
        )
        conn.execute(
            "INSERT INTO entities(id, canonical_name, entity_type, description, confidence, status)"
            " VALUES('entity-keep', '保留实体', 'product', '不应变化', 0.8, 'active')"
        )
        conn.execute(
            "INSERT INTO semantic_mentions VALUES('concept-keep', 'concept', ?)",
            (block["id"],),
        )
        conn.execute(
            "INSERT INTO semantic_mentions VALUES('entity-keep', 'entity', ?)",
            (block["id"],),
        )
        conn.execute(
            "INSERT INTO block_extractions VALUES(?, ?, 2, 'complete', 'now', NULL)",
            (block["id"], block["content_hash"]),
        )

    response = """{
      "claims": [{
        "statement": "该方案在当前数据集上更稳健",
        "claim_type": "conclusion",
        "scope": "当前数据集",
        "confidence": 0.9,
        "evidence_quote": "该方案在当前数据集上更稳健。"
      }]
    }"""
    result = extract_document_semantics(store, compiled["document_id"], llm_call=lambda _: response, claims_only=True)
    assert result["claims"] == 1

    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 1
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM semantic_mentions WHERE object_kind IN ('concept', 'entity')"
            ).fetchone()[0]
            == 2
        )
        assert conn.execute("SELECT COUNT(*) FROM block_extractions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM claim_extractions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1

    repeated = extract_document_semantics(store, compiled["document_id"], llm_call=lambda _: response, claims_only=True)
    assert repeated["extracted"] == 0
    assert repeated["skipped"] == 1


def test_claim_identity_includes_claim_type():
    source = "该方案可能更稳健。"

    def parsed(claim_type: str) -> dict:
        return validate_extraction(
            {
                "concepts": [],
                "entities": [],
                "claims": [
                    {
                        "statement": "该方案可能更稳健",
                        "claim_type": claim_type,
                        "scope": "当前数据集",
                        "confidence": 0.8,
                        "evidence_quote": source,
                    }
                ],
            },
            block_id="block-identity",
            block_content=source,
        )

    conclusion = parsed("conclusion")["claims"][0]
    hypothesis = parsed("hypothesis")["claims"][0]
    assert conclusion["id"] != hypothesis["id"]


def test_initialize_migrates_legacy_claim_type_column(tmp_path: Path):
    store = SemanticStore(tmp_path)
    store.root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store.path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO schema_meta VALUES ('claim_policy_version', '{CLAIM_POLICY_VERSION}');
            CREATE TABLE claims (
                id TEXT PRIMARY KEY,
                statement TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            );
            INSERT INTO claims VALUES ('legacy', '旧结论', '', 0.8, 'active');
            """
        )

    store.initialize()

    with store.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(claims)")}
        claim = conn.execute("SELECT claim_type FROM claims WHERE id = 'legacy'").fetchone()
        schema_version = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()["value"]
    assert "claim_type" in columns
    assert claim["claim_type"] == "conclusion"
    assert schema_version == "5"


def test_initialize_adds_relation_block_column_before_creating_its_index(tmp_path: Path):
    store = SemanticStore(tmp_path)
    store.root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(store.path) as conn:
        conn.executescript(
            f"""
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO schema_meta VALUES ('claim_policy_version', '{CLAIM_POLICY_VERSION}');
            CREATE TABLE relations (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                confidence REAL NOT NULL,
                evidence_id TEXT
            );
            """
        )

    store.initialize()

    with store.connect() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(relations)")}
        indexes = {row["name"] for row in conn.execute("PRAGMA index_list(relations)")}
    assert "block_id" in columns
    assert "idx_relations_block" in indexes


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
            '{"concepts": [], "entities": [], "claims": [{"statement": "该证据足以支持当前结论", "claim_type": "conclusion", "scope": "", "confidence": 0.8, "evidence_quote": "可追溯证据。"}]}',
        ]
    )

    result = extract_document_semantics(store, compiled["document_id"], llm_call=lambda _: next(responses))
    assert result["success"] is True
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1


def test_extractor_retries_transient_database_lock(tmp_path: Path, monkeypatch):
    note = _note(tmp_path, "## 结论\n\n该方案比基线更稳健。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    original_save = store.save_block_extraction
    calls = 0

    def locked_twice(**kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise sqlite3.OperationalError("database is locked")
        return original_save(**kwargs)

    monkeypatch.setattr(store, "save_block_extraction", locked_twice)
    monkeypatch.setattr("sidecar.semantic.extractor.time.sleep", lambda _delay: None)
    response = json.dumps(
        {
            "concepts": [],
            "entities": [],
            "claims": [
                {
                    "statement": "该方案比基线更稳健",
                    "claim_type": "conclusion",
                    "scope": "当前测试",
                    "confidence": 0.9,
                    "evidence_quote": "该方案比基线更稳健。",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = extract_document_semantics(store, compiled["document_id"], llm_call=lambda _prompt: response)

    assert result["success"] is True
    assert result["failed"] == 0
    assert calls == 3
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
            {{"block_id": "{blocks[0]["id"]}", "concepts": [], "entities": [],
              "claims": [{{"statement": "第一项方案更优", "claim_type": "conclusion", "scope": "", "confidence": 0.9, "evidence_quote": "证据一。"}}]}},
            {{"block_id": "{blocks[1]["id"]}", "concepts": [], "entities": [],
              "claims": [{{"statement": "第二项方案可能更稳健", "claim_type": "hypothesis", "scope": "", "confidence": 0.9, "evidence_quote": "证据二。"}}]}}
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
        return '{"concepts": [], "entities": [], "claims": [{"statement": "旧方案更好", "claim_type": "conclusion", "scope": "", "confidence": 0.8, "evidence_quote": "旧证据。"}]}'

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
        "---\ntopic: RAG > 检索\n---\n\n## 实验\n\n实验表明混合检索优于单一检索。\n",
    )
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    extract_document_semantics(
        store,
        compiled["document_id"],
        llm_call=lambda _: (
            """{
          "concepts": [], "entities": [],
          "claims": [{
            "statement": "混合检索优于单一检索",
            "claim_type": "conclusion",
            "scope": "RAG",
            "confidence": 0.9,
            "evidence_quote": "实验表明混合检索优于单一检索。"
          }]
        }"""
        ),
    )

    state = build_topic_state(store, "RAG > 检索")
    assert state["stats"] == {"documents": 1, "claims": 1}
    evidence = state["claims"][0]["evidence"][0]
    assert evidence["document_path"] == "Notes/RAG/测试.md"
    assert evidence["heading_path"] == ["实验"]
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
        llm_call=lambda _: (
            """{
          "concepts": [], "entities": [],
          "claims": [{
            "statement": "存在正文证据", "scope": "", "confidence": 0.9,
            "claim_type": "conclusion",
            "evidence_quote": "正文证据。"
          }]
        }"""
        ),
    )
    topic_state = build_topic_state(store, "RAG")
    materialize_topic_state(store, "RAG")
    note.unlink()

    topics = store.purge_missing_documents()
    assert topics == ["RAG"]
    materialize_topic_state(store, "RAG")
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
    assert store.view_dependencies(topic_state["topic_id"], "topic_state") == []


def test_compile_tracks_old_and_new_topics_without_rebuilding_unrelated_notes(tmp_path: Path):
    note = _note(tmp_path, "---\ntopic: A\n---\n\n原内容。\n")
    first = compile_note_semantics(tmp_path, note)
    assert first["affected_topics"] == ["A"]

    other = tmp_path / "Notes" / "B" / "无关.md"
    other.parent.mkdir(parents=True)
    other.write_text("---\ntopic: B\n---\n\n无关内容。\n", encoding="utf-8")
    compile_note_semantics(tmp_path, other)

    note.write_text("---\ntopic: C\n---\n\n修改后的内容。\n", encoding="utf-8")
    result = compile_semantic_batch(tmp_path, [note], extract=False)

    assert result["affected_topics"] == ["A", "C"]
    assert "B" not in result["affected_topics"]


def test_compile_snapshots_previous_objects_for_materialization_invalidation(tmp_path: Path):
    note = _note(tmp_path, "---\ntopic: A\n---\n\nBM25 用于关键词排序。\n")
    first = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    block = store.blocks_for_document(first["document_id"])[0]
    store.save_block_extraction(
        block_id=block["id"],
        block_hash=block["content_hash"],
        prompt_version=1,
        extracted_at="2026-07-20T00:00:00Z",
        concepts=[],
        entities=[
            {
                "id": "entity-bm25",
                "canonical_name": "BM25",
                "entity_type": "artifact",
                "description": "关键词排序",
                "confidence": 0.9,
            }
        ],
        claims=[],
    )
    note.write_text("---\ntopic: A\n---\n\n已移除旧实体。\n", encoding="utf-8")

    changed = compile_note_semantics(tmp_path, note)

    assert changed["affected_objects"] == [{"id": "entity-bm25", "kind": "entity", "name": "BM25"}]


def test_topic_state_records_dependencies_and_preserves_previous_file_on_publish_failure(tmp_path: Path, monkeypatch):
    note = _note(tmp_path, "---\ntopic: RAG\n---\n\n正文证据。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    extract_document_semantics(
        store,
        compiled["document_id"],
        llm_call=lambda _: (
            """{
          "concepts": [], "entities": [], "claims": [{
            "statement": "该证据支持当前结论", "claim_type": "conclusion",
            "scope": "RAG", "confidence": 0.9, "evidence_quote": "正文证据。"
          }]
        }"""
        ),
    )
    target = materialize_topic_state(store, "RAG")
    original = target.read_text(encoding="utf-8")
    state = build_topic_state(store, "RAG")
    dependencies = store.view_dependencies(state["topic_id"], "topic_state")
    assert {row["source_id"] for row in dependencies} == {
        compiled["document_id"],
        state["claims"][0]["id"],
        state["claims"][0]["evidence"][0]["block_id"],
    }

    def fail_replace(_source, _target):
        raise OSError("disk unavailable")

    monkeypatch.setattr("sidecar.semantic.topic_state.os.replace", fail_replace)
    try:
        materialize_topic_state(store, "RAG")
    except OSError as exc:
        assert "disk unavailable" in str(exc)
    else:
        raise AssertionError("expected atomic publish to fail")

    assert target.read_text(encoding="utf-8") == original
    assert store.view_dependencies(state["topic_id"], "topic_state") == dependencies


def test_topic_wiki_page_only_publishes_active_evidence_and_gates_pending_conflicts(tmp_path: Path):
    note = _note(tmp_path, "---\ntopic: RAG\n---\n\n正文证据。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    extract_document_semantics(
        store,
        compiled["document_id"],
        llm_call=lambda _: (
            """{
          "concepts": [], "entities": [], "claims": [{
            "statement": "该方案可能提升召回", "claim_type": "hypothesis",
            "scope": "RAG", "confidence": 0.8, "evidence_quote": "正文证据。"
          }]
        }"""
        ),
    )
    state = build_topic_state(store, "RAG")
    claim_id = state["claims"][0]["id"]
    evidence_id = state["claims"][0]["evidence"][0]["block_id"]

    page = build_topic_wiki_page(store, "RAG")
    assert "**假设：** 该方案可能提升召回" in page["content"]
    assert "Notes/RAG/测试.md" in page["content"]
    target = materialize_topic_wiki_page(store, "RAG")
    assert target == page["target"]
    assert target.exists()

    with store.connect() as conn:
        conn.execute(
            """INSERT INTO review_queue(id, item_kind, payload_json, reason, status, created_at)
               VALUES('conflict-gate', 'claim_conflict', ?, '待审阅', 'pending', 'now')""",
            (json.dumps({"claim_id": claim_id}),),
        )
    gated = build_topic_wiki_page(store, "RAG")
    assert gated["blocked_claim_ids"] == [claim_id]
    assert "暂不发布到本页" in gated["content"]
    assert "**假设：** 该方案可能提升召回" not in gated["content"]

    with store.connect() as conn:
        conn.execute("UPDATE evidence SET status = 'excluded' WHERE block_id = ?", (evidence_id,))
        conn.execute("UPDATE review_queue SET status = 'reviewed' WHERE id = 'conflict-gate'")
    excluded = build_topic_wiki_page(store, "RAG")
    assert excluded["claims"] == []


def test_claim_policy_upgrade_invalidates_legacy_claim_layer(tmp_path: Path):
    note = _note(tmp_path, "## 判断\n\n该方案在当前数据集上更稳健。\n")
    compiled = compile_note_semantics(tmp_path, note)
    store = SemanticStore(tmp_path)
    extract_document_semantics(
        store,
        compiled["document_id"],
        llm_call=lambda _: (
            """{
          "concepts": [], "entities": [],
          "claims": [{
            "statement": "该方案在当前数据集上更稳健",
            "claim_type": "conclusion",
            "scope": "当前数据集",
            "confidence": 0.9,
            "evidence_quote": "该方案在当前数据集上更稳健。"
          }]
        }"""
        ),
    )
    with store.connect() as conn:
        conn.execute("UPDATE schema_meta SET value = '1' WHERE key = 'claim_policy_version'")
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM block_extractions").fetchone()[0] == 1

    store.initialize()

    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM blocks").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM block_extractions").fetchone()[0] == 1
        assert (
            conn.execute("SELECT status FROM documents WHERE id = ?", (compiled["document_id"],)).fetchone()[0]
            == "parsed"
        )
