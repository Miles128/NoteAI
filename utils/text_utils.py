import json
import re
from pathlib import Path

from utils.logger import logger

_jieba_mod = None
_jieba_checked = False


def _get_jieba():
    global _jieba_mod, _jieba_checked
    if _jieba_checked:
        return _jieba_mod
    _jieba_checked = True
    try:
        import jieba as _jb

        _jieba_mod = _jb
    except ImportError:
        _jieba_mod = None
    return _jieba_mod


JIEBA_AVAILABLE = True  # resolved lazily by _get_jieba()

MIN_TAG_LENGTH = 2
OCCURRENCE_THRESHOLD = 3

_DATA_DIR = Path(__file__).resolve().parent / "data"


def _load_word_set(filename: str) -> frozenset:
    """加载 utils/data/ 下存储的词集合（泛词表 / 停用词表）。"""
    with open(_DATA_DIR / filename, encoding="utf-8") as f:
        return frozenset(json.load(f))


GENERIC_WORDS = _load_word_set("generic_words.json")

CHINESE_STOPWORDS = _load_word_set("chinese_stopwords.json")


def is_chinese_word(word: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", word))


def is_english_word(word: str) -> bool:
    """判断是否为英文词汇"""
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9]*$", word))


def _split_camel_case(text: str) -> str:
    """将 CamelCase 拆分为空格分隔的单词，用于后续分词
    ClaudeCode → Claude Code
    RAGSystem → RAG System
    """
    result = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", result)
    return result


def tokenize(text: str) -> list:
    """使用 jieba 对文本进行分词（支持中英文混合）

    Args:
        text: 待分词文本（文件名或任意文本）

    Returns:
        分词后的词汇列表，过滤掉空格和短词
    """
    if not text:
        return []

    text = _split_camel_case(text)

    _jb = _get_jieba()
    if _jb:
        try:
            tokens = _jb.lcut(text)
            return [t.strip() for t in tokens if t.strip() and len(t.strip()) >= MIN_TAG_LENGTH]
        except Exception as e:
            logger.warning(f"[tokenize] jieba lcut failed: {e}")

    text = re.sub(r"[（(].*?[）)]", "", text)
    parts = re.split(r"[-_\s——·|/\\\[\]【】：:，,。.！!？?、]+", text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) >= MIN_TAG_LENGTH]


def tokenize_filename(filename: str) -> list:
    """对文件名进行分词（去扩展名后分词）"""
    stem = Path(filename).stem
    return tokenize(stem)


def _normalize_for_match(s: str) -> str:
    """去除空格用于模糊匹配（"Claude Code" ↔ "ClaudeCode"）"""
    return re.sub(r"\s+", "", s).lower()


def _count_tag_occurrence(tag: str, filenames: list, case_insensitive: bool = True) -> int:
    tag_norm = _normalize_for_match(tag)
    if case_insensitive and is_english_word(tag):
        return sum(1 for fn in filenames if tag_norm in _normalize_for_match(fn.lower()))
    return sum(1 for fn in filenames if tag_norm in _normalize_for_match(fn))


def _is_generic_word(word: str) -> bool:
    """检查词是否为泛词（不表达主题区分度）

    统一使用 GENERIC_WORDS 集合，涵盖中文泛词、英文冠词/代词/常见动词/常见名词/介词/连词等。
    """
    return word.lower() in GENERIC_WORDS


def _is_meaningful_tag(tag: str) -> bool:
    """检查 tag 是否足够有意义

    纯中文：> 2 汉字
    纯英文：不在泛词列表中（GENERIC_WORDS，含冠词/代词/介词/连词/常见动词等）
    中英混合：> 8 字节 且 ≥ 2 个分词
    """
    if not tag or len(tag) < 2:
        return False
    chinese_chars = re.findall(r"[一-鿿]", tag)
    english_letters = re.findall(r"[a-zA-Z]", tag)
    has_chinese = len(chinese_chars) > 0
    has_english = len(english_letters) > 0
    if has_chinese and has_english:
        byte_len = len(tag.encode("utf-8"))
        token_count = len(tokenize(tag))
        return byte_len > 8 and token_count >= 2
    if has_chinese:
        return len(chinese_chars) > 2
    if has_english:
        return tag.lower() not in GENERIC_WORDS
    return False


def parse_frontmatter(text: str):
    """Parse YAML frontmatter from markdown text.

    Returns (meta_dict, body_str). If no frontmatter is found, returns
    (None, original_text).
    """
    import re

    import yaml

    m = re.match(r"^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---", text.lstrip("\ufeff"))
    if not m:
        return None, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    body_start = m.end()
    body = text.lstrip("\ufeff")[body_start:]
    return meta, body


def write_frontmatter(meta: dict | None, body: str, *, had_bom: bool = False) -> str:
    """Reconstruct file content from frontmatter dict and body text.

    If *meta* is ``None`` or empty, returns just the body (no frontmatter block).
    Otherwise returns ``---\\n<yaml>\\n---\\n<body>``.
    """
    import yaml

    prefix = "\ufeff" if had_bom else ""
    if not meta:
        return prefix + body
    fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
    return prefix + "---\n" + fm + "\n---\n" + body.lstrip("\n")
