"""Schema-constrained semantic extraction with evidence validation."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone

from sidecar.semantic.ids import content_hash, normalize_text, stable_id
from sidecar.semantic.store import SemanticStore

PROMPT_VERSION = 3
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_ENTITY_TYPES = {"person", "organization", "product", "model", "protocol", "artifact", "other"}
_CLAIM_TYPES = {"conclusion", "hypothesis"}
_BATCH_MAX_BLOCKS = 8
_BATCH_MAX_CHARS = 12_000
_SQLITE_LOCK_RETRIES = 4
_SQLITE_LOCK_RETRY_DELAY = 0.05

# Claim is a deliberately narrower product concept than a logically verifiable
# sentence.  Requiring an explicit judgment marker gives the deterministic
# validator a semantic floor instead of trusting an LLM-supplied claim_type.
_CONCLUSION_MARKERS = re.compile(
    r"(?:"
    r"优于|劣于|不如|高于|低于|强于|弱于|胜过|落后于|相比|相较|"
    r"比.{1,30}(?:优|劣|好|差|高|低|强|弱|快|慢|稳健|可靠|有效|适合)|"
    r"更(?:优|劣|好|差|高|低|强|弱|快|慢|稳健|可靠|有效|适合)|"
    r"最(?:佳|优|差|高|低|强|弱|快|慢|重要|关键)|"
    r"提升|提高|改善|增强|增长|上升|增加|降低|下降|减少|削弱|恶化|"
    r"导致|造成|引发|使得|源于|取决于|影响|促进|抑制|有助于|归因于|因此|因而|"
    r"趋势|逐渐|持续|越来越|"
    r"预测|预计|将会|有望|"
    r"建议|推荐|应当|应该|值得|适合|不适合|"
    r"有效|无效|可靠|稳健|重要|关键|合理|可行|不足|优势|局限|风险|足以|难以|易于|较差|优秀|出色|"
    r"表明|证明|显示|发现|可见|得出结论|支持.{0,8}(?:结论|判断|假设|推断)|"
    r"outperform(?:s|ed)?|better|worse|higher|lower|improv(?:e|es|ed|ement)|"
    r"increas(?:e|es|ed)|decreas(?:e|es|ed)|caus(?:e|es|ed)|leads?\s+to|"
    r"recommend(?:s|ed)?|should|effective|reliable|risk"
    r")",
    re.IGNORECASE,
)
_HYPOTHESIS_MARKERS = re.compile(
    r"(?:可能|或许|也许|推测|猜想|假设|尚待|有待|待验证|待检验|未验证|"
    r"如果|若(?:是|在|能|可|将|要|有|无)|倘若|may|might|could|possibly|perhaps|"
    r"hypothes(?:is|ize|ized)|unverified)",
    re.IGNORECASE,
)


class ExtractionValidationError(ValueError):
    pass


def _bounded_confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ExtractionValidationError("confidence 必须是数字") from exc
    if not 0 <= number <= 1:
        raise ExtractionValidationError("confidence 必须在 0 到 1 之间")
    return number


def parse_extraction_json(raw: str) -> dict:
    text = _FENCE.sub("", raw.strip()).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExtractionValidationError(f"LLM 输出不是合法 JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ExtractionValidationError("LLM 输出根节点必须是对象")
    return data


def _claim_has_required_judgment(statement: str, claim_type: str) -> bool:
    """Return whether a candidate clears the product-level Claim gate.

    This intentionally rejects plain attributes, counts, dates, definitions and
    factual fragments such as ``75+ 模型`` or ``支持 75 种模型`` even if the LLM
    labels them as conclusion.  Quantitative findings remain eligible when the
    statement explicitly expresses a comparison, change, causal judgment, or
    another supported conclusion marker.
    """
    if claim_type == "hypothesis":
        return _HYPOTHESIS_MARKERS.search(statement) is not None
    return _CONCLUSION_MARKERS.search(statement) is not None


def _retry_sqlite_lock(operation: Callable[[], object]) -> object:
    """Retry a short semantic write only when SQLite reports lock contention."""
    for attempt in range(_SQLITE_LOCK_RETRIES):
        try:
            return operation()
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == _SQLITE_LOCK_RETRIES - 1:
                raise
            time.sleep(_SQLITE_LOCK_RETRY_DELAY * (2**attempt))
    raise AssertionError("unreachable")


def validate_extraction(
    data: dict,
    *,
    block_id: str,
    block_content: str,
    block_type: str = "paragraph",
) -> dict:
    """Validate and canonicalize one block extraction.

    Claims without an exact source quote are rejected rather than downgraded.
    """
    result: dict[str, list[dict]] = {"concepts": [], "entities": [], "claims": []}
    normalized_block = normalize_text(block_content)

    for item in data.get("concepts", []):
        if not isinstance(item, dict):
            raise ExtractionValidationError("concepts 元素必须是对象")
        name = normalize_text(str(item.get("name") or ""))
        if not name:
            raise ExtractionValidationError("concept 缺少 name")
        result["concepts"].append(
            {
                "id": stable_id("con", name.casefold()),
                "canonical_name": name,
                "description": normalize_text(str(item.get("description") or "")),
                "confidence": _bounded_confidence(item.get("confidence", 0.5)),
            }
        )

    for item in data.get("entities", []):
        if not isinstance(item, dict):
            raise ExtractionValidationError("entities 元素必须是对象")
        name = normalize_text(str(item.get("name") or ""))
        entity_type = normalize_text(str(item.get("type") or "other")).lower()
        if not name:
            raise ExtractionValidationError("entity 缺少 name")
        if entity_type not in _ENTITY_TYPES:
            raise ExtractionValidationError(f"不支持的 entity type: {entity_type}")
        result["entities"].append(
            {
                "id": stable_id("ent", entity_type, name.casefold()),
                "canonical_name": name,
                "entity_type": entity_type,
                "description": normalize_text(str(item.get("description") or "")),
                "confidence": _bounded_confidence(item.get("confidence", 0.5)),
            }
        )

    raw_claims = data.get("claims", [])
    if not isinstance(raw_claims, list):
        raise ExtractionValidationError("claims 必须是数组")
    if block_type == "code":
        return result

    for item in raw_claims:
        if not isinstance(item, dict):
            raise ExtractionValidationError("claims 元素必须是对象")
        statement = normalize_text(str(item.get("statement") or ""))
        scope = normalize_text(str(item.get("scope") or ""))
        quote = normalize_text(str(item.get("evidence_quote") or ""))
        claim_type = normalize_text(str(item.get("claim_type") or "")).lower()
        # Claim-level failures reject only that candidate. One bad candidate
        # must not discard valid Concepts, Entities, or Claims from the block.
        if not statement:
            continue
        if claim_type not in _CLAIM_TYPES:
            continue
        if not _claim_has_required_judgment(statement, claim_type):
            continue
        if not quote:
            continue
        if quote not in normalized_block:
            continue
        try:
            confidence = _bounded_confidence(item.get("confidence", 0.5))
        except ExtractionValidationError:
            continue
        claim_id = stable_id("clm", claim_type, statement.casefold(), scope.casefold())
        quote_hash = content_hash(quote)
        result["claims"].append(
            {
                "id": claim_id,
                "statement": statement,
                "scope": scope,
                "claim_type": claim_type,
                "confidence": confidence,
                "evidence": {
                    "id": stable_id("evd", claim_id, block_id, quote_hash),
                    "claim_id": claim_id,
                    "block_id": block_id,
                    "quote_hash": quote_hash,
                },
            }
        )
    return result


def build_extraction_prompt(*, block_id: str, heading_path: str, content: str, block_type: str = "paragraph") -> str:
    return f"""你是 NoteAI 的语义编译器。只抽取当前原文明确支持的知识，不补充外部知识。

块 ID：{block_id}
块类型：{block_type}
章节：{heading_path or "（无）"}
原文：
<source>
{content}
</source>

只输出一个 JSON 对象，不要 Markdown 代码围栏：
{{
  "concepts": [{{"name": "概念名", "description": "原文内定义", "confidence": 0.0}}],
  "entities": [{{"name": "实体名", "type": "person|organization|product|model|protocol|artifact|other", "description": "原文内描述", "confidence": 0.0}}],
  "claims": [{{"statement": "作者得出的结论或提出的假设", "claim_type": "conclusion|hypothesis", "scope": "适用范围，可为空", "confidence": 0.0, "evidence_quote": "从原文逐字复制的短证据"}}]
}}

规则：
1. Claim 不是“任何可验证陈述”。只有作者明确得出的评价、比较、因果、趋势、预测、推荐等结论，才标为 conclusion。
2. 只有作者明确提出、尚待验证或带条件成立的推测/研究命题，才标为 hypothesis。
3. 定义、术语解释、产品属性、日期数字、背景事实、命令/参数/API/配置说明、安装步骤、操作指引、示例、代码行为复述，一律不要放进 claims。
4. 例如“75+ 模型”“支持 75 种模型”“运行 uv sync 安装依赖”“--port 指定端口”“Python 3.10 发布于 2021 年”都不是 Claim；“在该数据集上混合检索优于纯向量检索”才是 conclusion；“增大上下文窗口可能降低召回精度”可作为 hypothesis。
5. 代码块的 claims 必须为空；命令和说明仍可抽取 Concept/Entity。
6. evidence_quote 必须逐字来自原文，不能改写；没有明确证据的内容不要输出。
7. confidence 表示抽取把握，范围 0 到 1；无内容时返回对应空数组。"""


def build_repair_prompt(original_prompt: str, invalid_output: str, error: str) -> str:
    return f"""{original_prompt}

你上次的输出未通过编译器校验：{error}
<invalid-output>
{invalid_output[:6000]}
</invalid-output>
请只修复 JSON 结构或证据字段，仍然只能使用 source 中的原文。只输出修复后的 JSON。"""


def build_batch_extraction_prompt(blocks: list[dict]) -> str:
    sources = []
    for block in blocks:
        sources.append(
            f"""<block id="{block["id"]}" type="{block["type"]}">
章节：{block["heading"] or "（无）"}
原文：
{block["content"]}
</block>"""
        )
    joined = "\n\n".join(sources)
    return f"""你是 NoteAI 的语义编译器。只抽取各 Block 原文明确支持的知识，不补充外部知识。

{joined}

必须为每个输入 block_id 返回一项，不能遗漏、合并或改写 block_id。只输出 JSON：
{{
  "blocks": [
    {{
      "block_id": "输入中的原始 ID",
      "concepts": [{{"name": "概念名", "description": "原文内定义", "confidence": 0.0}}],
      "entities": [{{"name": "实体名", "type": "person|organization|product|model|protocol|artifact|other", "description": "原文内描述", "confidence": 0.0}}],
      "claims": [{{"statement": "作者得出的结论或提出的假设", "claim_type": "conclusion|hypothesis", "scope": "适用范围，可为空", "confidence": 0.0, "evidence_quote": "只从该 block 原文逐字复制"}}]
    }}
  ]
}}

规则：
1. Claim 不是普通事实。只允许作者的评价/比较/因果/趋势/预测/推荐等结论（conclusion），或明确待验证的假设/推测（hypothesis）。
2. 定义、术语解释、属性、数量（如“75+ 模型”“支持 75 种模型”）、日期数字、背景事实、命令/参数/API/配置说明、步骤、操作指引、示例、代码行为复述不得进入 claims；code 类型 Block 的 claims 必须为空。
3. evidence_quote 必须逐字来自同一 block_id 的原文，不能跨 Block、不能改写。
4. 没有结论或假设的 Block 也必须返回，claims 为空；三个数组都无内容时均为空。
5. confidence 表示抽取把握，范围 0 到 1；只输出 JSON。"""


def build_claim_extraction_prompt(*, block_id: str, heading_path: str, content: str, block_type: str) -> str:
    return f"""你是 NoteAI 的 Claim 编译器。本次只抽取结论与假设，不抽取 Concept 或 Entity。

块 ID：{block_id}
块类型：{block_type}
章节：{heading_path or "（无）"}
原文：
<source>
{content}
</source>

只输出 JSON：
{{"claims": [{{"statement": "作者得出的结论或提出的假设", "claim_type": "conclusion|hypothesis", "scope": "适用范围，可为空", "confidence": 0.0, "evidence_quote": "从原文逐字复制"}}]}}

只有评价、比较、因果、趋势、预测、推荐等结论，或明确待验证的假设/推测才可进入 claims。
定义、术语解释、属性、数量（如“75+ 模型”“支持 75 种模型”）、日期数字、背景事实、命令、参数、API、配置、步骤、操作指引、示例和代码说明都不是 Claim。
code 类型块必须返回空 claims。evidence_quote 必须逐字来自原文。无结论或假设时返回 {{"claims": []}}。"""


def build_batch_claim_extraction_prompt(blocks: list[dict]) -> str:
    sources = []
    for block in blocks:
        sources.append(
            f"""<block id="{block["id"]}" type="{block["type"]}">
章节：{block["heading"] or "（无）"}
原文：
{block["content"]}
</block>"""
        )
    return f"""你是 NoteAI 的 Claim 编译器。本次只抽取结论与假设，不抽取 Concept 或 Entity。

{chr(10).join(sources)}

必须为每个 block_id 返回一项，只输出 JSON：
{{"blocks": [{{"block_id": "原始 ID", "claims": [{{"statement": "作者得出的结论或提出的假设", "claim_type": "conclusion|hypothesis", "scope": "适用范围，可为空", "confidence": 0.0, "evidence_quote": "同一块原文逐字复制"}}]}}]}}

只允许评价、比较、因果、趋势、预测、推荐等结论，或明确待验证的假设/推测。
定义、术语解释、属性、数量（如“75+ 模型”“支持 75 种模型”）、日期数字、背景事实、命令、参数、API、配置、步骤、操作指引、示例和代码说明都不是 Claim。
code 类型块和没有结论/假设的块必须返回空 claims。不能遗漏、合并或改写 block_id。"""


def validate_batch_extraction(data: dict, blocks: list[dict]) -> dict[str, dict]:
    raw_items = data.get("blocks")
    if not isinstance(raw_items, list):
        raise ExtractionValidationError("批量输出缺少 blocks 数组")
    expected = {block["id"]: block for block in blocks}
    actual: dict[str, dict] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            raise ExtractionValidationError("blocks 元素必须是对象")
        block_id = str(item.get("block_id") or "")
        if block_id not in expected:
            raise ExtractionValidationError(f"未知 block_id: {block_id}")
        if block_id in actual:
            raise ExtractionValidationError(f"重复 block_id: {block_id}")
        actual[block_id] = validate_extraction(
            item,
            block_id=block_id,
            block_content=expected[block_id]["content"],
            block_type=expected[block_id]["type"],
        )
    missing = set(expected) - set(actual)
    if missing:
        raise ExtractionValidationError(f"批量输出遗漏 block_id: {', '.join(sorted(missing))}")
    return actual


def _group_extraction_blocks(blocks: list[dict]) -> list[list[dict]]:
    groups: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0
    for block in blocks:
        size = len(block["content"]) + len(block["heading"]) + 80
        if current and (len(current) >= _BATCH_MAX_BLOCKS or current_chars + size > _BATCH_MAX_CHARS):
            groups.append(current)
            current = []
            current_chars = 0
        current.append(block)
        current_chars += size
    if current:
        groups.append(current)
    return groups


def extract_document_semantics(
    store: SemanticStore,
    document_id: str,
    *,
    llm_call: Callable[[str], str] | None = None,
    claims_only: bool = False,
) -> dict:
    """Extract all pending blocks, degrading cleanly when no LLM is configured."""
    use_batch = llm_call is None
    if llm_call is None:
        from utils.llm_utils import call_llm_raw, check_api_config

        ready, message = check_api_config()
        if not ready:
            store.set_document_status(document_id, "pending_extraction")
            return {"success": True, "pending": True, "message": message, "extracted": 0, "failed": 0}

        def configured_llm_call(prompt: str) -> str:
            return call_llm_raw(prompt, temperature=0.1, max_tokens=6500)

        llm_call = configured_llm_call

    document = store.document_by_id(document_id)
    if document is None:
        raise ValueError(f"语义文档不存在: {document_id}")

    extracted = 0
    claim_count = 0
    skipped = 0
    failures: list[dict] = []
    pending_blocks: list[dict] = []
    for stored_block in store.blocks_for_document(document_id):
        is_current = store.claim_extraction_is_current if claims_only else store.extraction_is_current
        if is_current(stored_block["id"], stored_block["content_hash"], PROMPT_VERSION):
            skipped += 1
            continue
        pending_blocks.append(
            {
                "id": stored_block["id"],
                "hash": stored_block["content_hash"],
                "type": stored_block["block_type"],
                "heading": " > ".join(json.loads(stored_block["heading_path_json"])),
                "content": stored_block["content"],
            }
        )

    def source_is_current() -> bool:
        source = store.workspace / document["path"]
        return source.is_file() and content_hash(source.read_text(encoding="utf-8")) == document["content_hash"]

    def save_result(block: dict, parsed: dict, now: str) -> None:
        nonlocal extracted, claim_count
        if not source_is_current():
            raise RuntimeError("源文件在语义抽取期间发生变化，已丢弃本次结果")
        if claims_only:
            _retry_sqlite_lock(
                lambda: store.save_block_claim_extraction(
                    block_id=block["id"],
                    block_hash=block["hash"],
                    prompt_version=PROMPT_VERSION,
                    extracted_at=now,
                    claims=parsed["claims"],
                )
            )
        else:
            _retry_sqlite_lock(
                lambda: store.save_block_extraction(
                    block_id=block["id"],
                    block_hash=block["hash"],
                    prompt_version=PROMPT_VERSION,
                    extracted_at=now,
                    **parsed,
                )
            )
        extracted += 1
        claim_count += len(parsed["claims"])

    def extract_single(block: dict) -> None:
        nonlocal failures
        now = datetime.now(timezone.utc).isoformat()
        try:
            prompt_builder = build_claim_extraction_prompt if claims_only else build_extraction_prompt
            prompt = prompt_builder(
                block_id=block["id"],
                heading_path=block["heading"],
                content=block["content"],
                block_type=block["type"],
            )
            raw = llm_call(prompt)
            try:
                parsed = validate_extraction(
                    parse_extraction_json(raw),
                    block_id=block["id"],
                    block_content=block["content"],
                    block_type=block["type"],
                )
            except ExtractionValidationError as first_error:
                repaired = llm_call(build_repair_prompt(prompt, raw, str(first_error)))
                parsed = validate_extraction(
                    parse_extraction_json(repaired),
                    block_id=block["id"],
                    block_content=block["content"],
                    block_type=block["type"],
                )
            save_result(block, parsed, now)
        except Exception as exc:
            marker = store.mark_claim_extraction_failed if claims_only else store.mark_extraction_failed
            error = str(exc)
            try:
                _retry_sqlite_lock(lambda: marker(block["id"], block["hash"], PROMPT_VERSION, now, error))
            except Exception as marker_exc:
                error = f"{error}; 记录失败状态失败: {marker_exc}"
            failures.append({"block_id": block["id"], "error": error})

    if use_batch:
        for group in _group_extraction_blocks(pending_blocks):
            prompt = build_batch_claim_extraction_prompt(group) if claims_only else build_batch_extraction_prompt(group)
            try:
                raw = llm_call(prompt)
                try:
                    parsed_group = validate_batch_extraction(parse_extraction_json(raw), group)
                except ExtractionValidationError as first_error:
                    repaired = llm_call(build_repair_prompt(prompt, raw, str(first_error)))
                    parsed_group = validate_batch_extraction(parse_extraction_json(repaired), group)
                now = datetime.now(timezone.utc).isoformat()
                for pending_block in group:
                    save_result(pending_block, parsed_group[pending_block["id"]], now)
            except Exception:
                # Preserve correctness over speed: a malformed batch falls back
                # to the established single-block validator and retry path.
                for pending_block in group:
                    extract_single(pending_block)
    else:
        for pending_block in pending_blocks:
            extract_single(pending_block)

    status = "semantic" if not failures else "partial"
    _retry_sqlite_lock(lambda: store.set_document_status(document_id, status))
    return {
        "success": not failures,
        "pending": False,
        "extracted": extracted,
        "claims": claim_count,
        "skipped": skipped,
        "failed": len(failures),
        "failures": failures,
    }
