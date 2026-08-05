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

PROMPT_VERSION = 4
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
    r"提升|提高|改善|增强(?![生学模型器])|增长|上升|增加|降低|下降|减少|削弱|恶化|"
    r"导致|造成|引发|使得|源于|取决于|影响|促进|抑制|有助于|归因于|因此|因而|"
    r"趋势|逐渐|持续|越来越|"
    r"预测|预计|将会|有望|"
    r"建议|推荐|应当|应该|值得|适合|不适合|"
    r"有效|无效|可靠|稳健|重要|关键|合理|可行|不足|优势|局限|风险|足以|难以|易于|较差|优秀|出色|"
    r"表明|证明|显示|发现|可见|得出结论|支持.{0,8}(?:结论|判断|假设|推断)|"
    r"outperform(?:s|ed)?|better|worse|higher|lower|improv(?:e|es|ed|ement)|"
    r"increas(?:e|es|ed)|decreas(?:e|es|ed)|reduc(?:e|es|ed)|caus(?:e|es|ed)|leads?\s+to|"
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

# 噪声对象名确定性过滤：拦截把文件名、章节标题、纯符号/数字等抽成实体/概念。
_FILE_SUFFIX_RE = re.compile(
    r"\.(?:md|markdown|txt|docx?|pdf|pptx?|xlsx?|yaml|yml|json|csv|py|js|ts|jsx|tsx|css|html?|sql|sh|toml|ini|cfg)$",
    re.IGNORECASE,
)
_VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,3}(?:[-+][a-z0-9.-]+)?$", re.IGNORECASE)
# 文件/章节序号前缀（00_、01-、1.2_）：NoteAI 文件名规范 ``00_xxx.md`` 的头部。
_HEADING_NUMBER_RE = re.compile(r"^\d+(?:[._-]\d+)*[._-]")
# 多对象合并名：LLM 常把多个实体拼成一个（斜杠/全角斜杠/顿号分隔），如 ``GPT-4o/5``、
# ``华佗（华为）/ 润达医疗大模型``、``创客贴/来画/水母智能/Nui``。
_SEPARATOR_MERGE_RE = re.compile(r"[/、／]")
# 域名/网址样式（learnprompting.org、openai.com）：顶级域至少两个字母，
# 排除 ``Qwen2.5``、``GLM 5.2`` 这类带版本号的模型名。
_DOMAIN_RE = re.compile(r"^[\w-]+\.[a-zA-Z]{2,}$")
# 隐藏文件/目录样式（.env、.gitignore、.claude）：第二字符小写或数字；
# ``.NET``、``.NET Core`` 这类大写产品名不匹配，予以放行。
_DOTFILE_RE = re.compile(r"^\.[a-z0-9][\w.-]*$")
# MCP/工具引用语法（@file、@folder、@tool、@git）：LLM 把代码注释/提示词里的
# 引用记号当成了对象名。
_AT_REFERENCE_RE = re.compile(r"^@[\w-]+")
# 全大写+下划线环境变量/配置键（AGENT_TRIGGERS、API_KEY）：不是实体。
# 必须包含下划线，避免误杀 RAG、BM25 这类全大写缩写。
_UPPER_UNDERSCORE_RE = re.compile(r"^[A-Z][A-Z0-9_]*_[A-Z0-9_]+$")
# 数字+单位开头（200K token、8GB显存）：量纲描述不是实体。
# 要求数字后紧跟 K/M/B 单位字母，避免误杀 36 氪、11 Labs 这类专名。
_NUMERIC_PREFIX_RE = re.compile(r"^\d+[KMBkmb]+\s|^\d+\s*[×xX*]\s*\d")
# 长句含中文标点（3步申请，24小时放款）：广告/流程描述被当成概念。
_LONG_SENTENCE_RE = re.compile(r"[，。；、！？]")


# 文章标题/资料名特征：LLM 经常把文档标题、专栏名抽成对象。
_TITLE_MARKER_RE = re.compile(
    r"(?:报告|指南|路线图|全景|速成|学习笔记|白皮书|专栏|合集|面试题|实践指南|入门教程|官方文档|源码解析|全梳理|知识体系全梳理)",
    re.IGNORECASE,
)

# Prompt-level gate, applied BEFORE the LLM generates: noise patterns and
# variant-spelling dedup rules are spelled out so the model never emits them
# in the first place. validate_extraction below remains the hard fallback.
_OBJECT_NAME_RULES = """实体与概念名称必须是简洁规范名：
- 先去除括号注释再输出：「RAG（检索增强生成）」「可灵(Kling)」应输出为「RAG」「可灵」；括号内容只是解释，不是名称的一部分。
- 同一对象只输出一次：不要同时输出「RAG」与「RAG（检索增强生成）」这类变体；名称内不夹空格（「R A G」应写为「RAG」），统一用最简洁写法。
- 不得输出：标题类短语（含「报告、指南、路线图、全景、速成、学习笔记、白皮书、专栏、合集、面试题、实践指南、入门教程、官方文档、源码解析、全梳理」等标题词）、@开头的引用（如 @file、@tool）、全大写下划线标记（如 AGENT_TRIGGERS）、带单位的数字短语（如 200K token、3步申请）、域名、点开头文件名（如 .env）、含标点的完整句子、纯符号或纯数字。"""


def _is_noise_object_name(name: str) -> bool:
    """Return True for names that are almost certainly not a real entity/concept.

    Deterministic gate on top of the LLM schema: file names, heading-like names,
    pure symbols/digits, flag-style tokens (``--ar``), merged multi-object names
    (``A/B``), and domain names must never become semantic objects.  Keeps valid
    short names (e.g. ``RAG``, ``模型``), versioned model names (``GLM 5.2``)
    and capitalised product names (``.NET``).
    """
    if not name or len(name) < 2:
        return True
    stripped = name.strip()
    if stripped != name:
        return True  # 首尾空白说明抽取拼接了原文以外的内容
    if name.endswith((".", "-", "_")):
        return True
    if name.startswith("."):
        if _DOTFILE_RE.match(name):
            return True  # .env、.gitignore、.claude 这类隐藏文件/目录
    elif name.startswith(("-", "_", "--")):
        return True  # --ar、-s、_private 这类标志/临时命名
    if _AT_REFERENCE_RE.match(name):
        return True  # @file、@tool 这类 MCP/工具引用语法
    if _UPPER_UNDERSCORE_RE.fullmatch(name):
        return True  # AGENT_TRIGGERS 这类环境变量/配置键
    if _NUMERIC_PREFIX_RE.match(name):
        return True  # 200K token、8GB显存、3×3网格 这类量纲描述
    if len(name) > 20 and _LONG_SENTENCE_RE.search(name):
        return True  # 长句含中文标点：广告/流程描述被当成对象
    if _TITLE_MARKER_RE.search(name):
        return True  # 文章标题/资料名：xxx报告/指南/路线图/速成/CSDN
    if _FILE_SUFFIX_RE.search(name):
        return True
    if _VERSION_RE.fullmatch(name):
        return True
    if _HEADING_NUMBER_RE.match(name):
        return True  # ``06_四阶十二步法``、``01-基础`` 这类文件名/序号标题
    if _SEPARATOR_MERGE_RE.search(name):
        return True  # 斜杠/顿号分隔的多个对象被 LLM 合并成了一个名字
    if _DOMAIN_RE.fullmatch(name):
        return True  # ``learnprompting.org`` 域名不是实体
    if not any(ch.isalpha() for ch in name):
        return True  # 纯数字/符号/版本号（isalpha 覆盖中文）
    return False


# First-person subjective opinions (我/本人 + 看法、偏好、喜恶) are deliberately
# NOT Claims: they express personal taste rather than an author judgment that
# could be supported or refuted by evidence.  Third-person attributions such as
# "作者认为 …" stay eligible because they state the author's position as a
# verifiable fact about the source.
_OPINION_MARKERS = re.compile(
    r"(?:"
    r"我认为|我觉得|我个人(?:认为|觉得|的看法|的观点|而言)|在我看来|依我(?:之见|看来)|"
    r"我的(?:观点|看法|立场|经验)|主观(?:上|地)?(?:认为|觉得|看|判断)|"
    r"说句(?:公道话|实话|心里话)|坦白(?:地)?说|个人而言|以我之见|"
    r"我(?:个人)?(?:更)?(?:喜欢|偏爱|偏好|欣赏|看好)|我(?:更)?(?:倾向|倾向于|愿意)|"
    r"我不(?:喜欢|看好|赞成|同意|认为|觉得)|我(?:坚决)?(?:支持|反对)这个观点|"
    r"凭(?:感觉|直觉)|感觉上|直觉上|"
    r"i\s+(?:think|believe|feel|prefer|like|recommend|personally)"
    r")",
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


# 标点/空白（含全角）在证据引文中属于可容忍差异；文字序列必须保持逐字一致。
_QUOTE_PUNCT_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def _quote_matches(quote: str, normalized_block: str) -> bool:
    """证据引文必须逐字来自原文，但容忍首尾标点与空白差异。

    LLM 复制证据时常多带/少带句号、引号或换行；只要去掉标点空白后的文字序列
    仍是原文子序列（且足够长），就接受，避免因标点差异误杀全部命题。
    """
    if quote in normalized_block:
        return True
    core = quote.strip(" \t\u3000，。、；：？！,.!?;:\"'“”‘’（）()【】[]《》<>-–—…")
    if core and core in normalized_block:
        return True
    compact_quote = _QUOTE_PUNCT_RE.sub("", quote)
    compact_block = _QUOTE_PUNCT_RE.sub("", normalized_block)
    return len(compact_quote) >= 8 and compact_quote in compact_block


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

    First-person opinions (我认为/我觉得/我的观点/主观上 …) never enter the
    conclusion stream regardless of the LLM-supplied claim_type: personal
    taste cannot be supported or refuted, so an opinion-labeled candidate is
    dropped just like any other pseudo-claim.
    """
    if _OPINION_MARKERS.search(statement):
        return False
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
    rejections: dict[str, int] | None = None,
) -> dict:
    """Validate and canonicalize one block extraction.

    Claims without an exact source quote are rejected rather than downgraded.
    ``rejections`` collects per-rule drop counts for diagnostics (claims).
    """
    result: dict[str, list[dict]] = {"concepts": [], "entities": [], "claims": []}
    normalized_block = normalize_text(block_content)

    for item in data.get("concepts", []):
        if not isinstance(item, dict):
            raise ExtractionValidationError("concepts 元素必须是对象")
        name = normalize_text(str(item.get("name") or ""))
        if not name:
            raise ExtractionValidationError("concept 缺少 name")
        if _is_noise_object_name(name):
            continue
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
        if _is_noise_object_name(name):
            continue
        result["entities"].append(
            {
                # ID 只按名称生成，不包含 entity_type，确保同名实体合并为一个
                "id": stable_id("ent", name.casefold()),
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
            if rejections is not None:
                rejections["claims_no_statement"] = rejections.get("claims_no_statement", 0) + 1
            continue
        if claim_type not in _CLAIM_TYPES:
            if rejections is not None:
                rejections["claims_no_type"] = rejections.get("claims_no_type", 0) + 1
            continue
        if not _claim_has_required_judgment(statement, claim_type):
            if rejections is not None:
                rejections["claims_no_judgment"] = rejections.get("claims_no_judgment", 0) + 1
            continue
        if not quote:
            if rejections is not None:
                rejections["claims_no_quote"] = rejections.get("claims_no_quote", 0) + 1
            continue
        if not _quote_matches(quote, normalized_block):
            if rejections is not None:
                rejections["claims_quote_mismatch"] = rejections.get("claims_quote_mismatch", 0) + 1
            continue
        try:
            confidence = _bounded_confidence(item.get("confidence", 0.5))
        except ExtractionValidationError:
            if rejections is not None:
                rejections["claims_bad_confidence"] = rejections.get("claims_bad_confidence", 0) + 1
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
5. 第一人称主观意见（“我认为/我觉得/我的观点/主观上/我更偏好……”）不是 Claim；转述他人立场的“作者认为/论文指出”仍可抽取。
6. 代码块的 claims 必须为空；命令和说明仍可抽取 Concept/Entity。
7. evidence_quote 必须逐字来自原文，不能改写；没有明确证据的内容不要输出。
8. confidence 表示抽取把握，范围 0 到 1；无内容时返回对应空数组。
9. 实体与概念必须是领域内稳定的具名对象或术语；文件名、章节标题、目录名、列表序号、纯数字/日期/版本号、命令参数（如 --port）、URL、邮箱、代码标识符、临时命名一律不得抽取为实体或概念。
10. {_OBJECT_NAME_RULES}"""


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
3. 第一人称主观意见（“我认为/我觉得/我的观点/主观上/我更偏好……”）不是 Claim；“作者认为/论文指出”等转述立场仍可抽取。
3. evidence_quote 必须逐字来自同一 block_id 的原文，不能跨 Block、不能改写。
4. 没有结论或假设的 Block 也必须返回，claims 为空；三个数组都无内容时均为空。
5. confidence 表示抽取把握，范围 0 到 1；只输出 JSON。
6. 实体与概念必须是领域内稳定的具名对象或术语；文件名、章节标题、目录名、列表序号、纯数字/日期/版本号、命令参数、URL、邮箱、代码标识符、临时命名一律不得抽取为实体或概念。
7. {_OBJECT_NAME_RULES}"""


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
第一人称主观意见（“我认为/我觉得/我的观点/主观上/我更偏好……”）不是 Claim；“作者认为/论文指出”等转述立场仍可抽取。
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
第一人称主观意见（“我认为/我觉得/我的观点/主观上/我更偏好……”）不是 Claim；“作者认为/论文指出”等转述立场仍可抽取。
code 类型块和没有结论/假设的块必须返回空 claims。不能遗漏、合并或改写 block_id。"""


def validate_batch_extraction(
    data: dict, blocks: list[dict], rejections: dict[str, int] | None = None
) -> dict[str, dict]:
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
            rejections=rejections,
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
    rejections: dict[str, int] = {}
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
                    rejections=rejections,
                )
            except ExtractionValidationError as first_error:
                repaired = llm_call(build_repair_prompt(prompt, raw, str(first_error)))
                parsed = validate_extraction(
                    parse_extraction_json(repaired),
                    block_id=block["id"],
                    block_content=block["content"],
                    block_type=block["type"],
                    rejections=rejections,
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
                    parsed_group = validate_batch_extraction(parse_extraction_json(raw), group, rejections=rejections)
                except ExtractionValidationError as first_error:
                    repaired = llm_call(build_repair_prompt(prompt, raw, str(first_error)))
                    parsed_group = validate_batch_extraction(
                        parse_extraction_json(repaired), group, rejections=rejections
                    )
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
    rejected_total = sum(rejections.values())
    if rejected_total:
        from utils.logger import logger

        logger.info(
            f"[semantic-extract] 文档 {document_id}: 拒绝 {rejected_total} 条命题候选 "
            f"(no_statement={rejections.get('claims_no_statement', 0)}, "
            f"no_type={rejections.get('claims_no_type', 0)}, "
            f"no_judgment={rejections.get('claims_no_judgment', 0)}, "
            f"no_quote={rejections.get('claims_no_quote', 0)}, "
            f"quote_mismatch={rejections.get('claims_quote_mismatch', 0)}, "
            f"bad_confidence={rejections.get('claims_bad_confidence', 0)})"
        )
    return {
        "success": not failures,
        "pending": False,
        "extracted": extracted,
        "claims": claim_count,
        "rejected_claims": rejected_total,
        "rejection_details": rejections,
        "skipped": skipped,
        "failed": len(failures),
        "failures": failures,
    }
