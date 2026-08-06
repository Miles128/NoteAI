import re
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.logger import logger
from utils.text_utils import (
    CHINESE_STOPWORDS,
    OCCURRENCE_THRESHOLD,
    _count_tag_occurrence,
    _is_generic_word,
    _normalize_for_match,
    is_chinese_word,
    is_english_word,
    parse_frontmatter,
    tokenize_filename,
    write_frontmatter,
)


def _collect_workspace_md_filenames(workspace_path: str) -> list[str]:
    """收集 Notes、wiki 文件夹中所有 MD 文件的文件名（只读文件名，不读内容）

    Args:
        workspace_path: 工作区根路径

    Returns:
        所有 md 文件的文件名列表（不含路径）
    """
    from utils.note_scanner import iter_note_files

    files = iter_note_files(workspace_path, folders=["Notes", "wiki"], include_surveys=True)
    return [path.name for path in files]


def _generate_english_pairs(english_words: list[str]) -> list[str]:
    """生成相邻英文单词的组合

    例如: ["Machine", "Learning"] -> ["MachineLearning", "Machine Learning"]
    """
    pairs = []
    for i in range(len(english_words) - 1):
        word1 = english_words[i]
        word2 = english_words[i + 1]
        pairs.append(word1 + word2)
        pairs.append(word1 + " " + word2)
        pairs.append(word1 + "-" + word2)
        pairs.append(word1 + "_" + word2)
    return pairs


def _is_word_in_accepted_pair(word: str, accepted_pairs: list[str], case_insensitive: bool = True) -> bool:
    """检查单词是否已被包含在已接受的双词组合中（忽略空格）

    例如: "Machine" 在 "MachineLearning" 或 "Machine Learning" 中则返回 True
    """
    word_norm = _normalize_for_match(word)
    for pair in accepted_pairs:
        if word_norm in _normalize_for_match(pair):
            return True
    return False


def split_filename_fields(filename: str) -> list[str]:
    """将文件名字段按分隔符拆分为独立的字段列表

    示例：
        "机器学习-神经网络-反向传播.md" → ["机器学习", "神经网络", "反向传播"]
        "Python_基础教程.md" → ["Python", "基础教程"]
        "React Hooks 详解.md" → ["React", "Hooks", "详解"]
        "设计模式——观察者模式.md" → ["设计模式", "观察者模式"]
    """
    stem = Path(filename).stem
    parts = re.split(r"[-_\s——·|/\\\[\]【】：:，,。.！!？?、]+", stem)
    return [p.strip() for p in parts if p.strip()]


def extract_tags_from_filename(file_path: str) -> list[str]:
    """基于文件名分词提取标签

    算法：
    1. 使用 jieba 对当前文件的文件名进行分词
    2. 按优先级处理：
       a. 英文双词组合：相邻英文单词组合，在文件名中出现次数 > 3 则加入
       b. 英文单词：单个英文单词，若未被包含在已接受的双词组合中，且出现次数 > 3 则加入
       c. 中文单词：排除中文停用词，出现次数 > 3 则加入
    3. 只对比文件名，不读取文件内容

    Args:
        file_path: 待打标签的文件路径

    Returns:
        标签字符串列表
    """
    from config import config

    if not config.workspace_path:
        return []

    file_path_obj = Path(file_path)

    tokens = tokenize_filename(file_path_obj.name)

    if not tokens:
        return []

    workspace_filenames = _collect_workspace_md_filenames(config.workspace_path)

    if not workspace_filenames:
        return []

    english_words = []
    chinese_words = []

    for token in tokens:
        if is_english_word(token):
            english_words.append(token)
        elif is_chinese_word(token):
            chinese_words.append(token)

    tags = []
    accepted_english_pairs = []

    if len(english_words) >= 2:
        pairs = _generate_english_pairs(english_words)
        seen_pairs = set()
        for pair in pairs:
            if pair.lower() in seen_pairs:
                continue
            seen_pairs.add(pair.lower())
            count = _count_tag_occurrence(pair, workspace_filenames)
            if count > OCCURRENCE_THRESHOLD:
                tags.append(pair)
                accepted_english_pairs.append(pair)

    for word in english_words:
        if _is_word_in_accepted_pair(word, accepted_english_pairs):
            continue
        count = _count_tag_occurrence(word, workspace_filenames)
        if count > OCCURRENCE_THRESHOLD:
            tags.append(word)

    for word in chinese_words:
        if word in CHINESE_STOPWORDS:
            continue
        count = _count_tag_occurrence(word, workspace_filenames)
        if count > OCCURRENCE_THRESHOLD:
            tags.append(word)

    seen = set()
    unique_tags = []
    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower not in seen and not _is_generic_word(tag):
            seen.add(tag_lower)
            unique_tags.append(tag)

    return unique_tags


def tag_files_by_filename(file_paths: list[str]) -> dict[str, list[str]]:
    """对一批 Markdown 文件基于文件名分词提取标签并添加 YAML front matter

    Args:
        file_paths: Markdown 文件路径列表

    Returns:
        {文件路径: 标签列表} 字典
    """
    if not file_paths:
        return {}

    results = {}
    for fp in file_paths:
        try:
            tags = extract_tags_from_filename(fp)
            if tags:
                add_yaml_frontmatter_to_file(fp, tags=tags)
                results[fp] = tags
        except Exception as e:
            logger.warning(f"[tag_files_by_filename] 处理失败 {fp}: {e}\n")

    return results


def generate_yaml_frontmatter(
    title: str = "",
    tags: list[str] | None = None,
    date: datetime | None = None,
    source: str = "",
    extra_fields: dict[str, Any] | None = None,
) -> str:
    """生成标准的 YAML front matter（仅包含 tags 和 source）

    参数：
        title: 文档标题
        tags: 标签列表
        date: 创建/处理日期（默认当前日期）
        source: 来源（URL或文件路径）
        extra_fields: 额外的自定义字段

    返回：
        完整的 YAML front matter 字符串（包含 --- 分隔符）
    """
    fields: dict[str, Any] = {}

    if title:
        fields["title"] = title

    fields["tags"] = tags if tags else []

    if date is None:
        date = datetime.now()
    fields["date"] = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)

    if source:
        fields["source"] = source

    if extra_fields:
        fields.update(extra_fields)

    return write_frontmatter(fields, "")


def parse_yaml_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """解析 Markdown 文件中的 YAML front matter

    参数：
        content: Markdown 文件完整内容

    返回：
        (frontmatter_dict, remaining_content)
    """
    meta, body = parse_frontmatter(content)
    if meta is None:
        return {}, content
    return meta, body.lstrip("\n")


def add_yaml_frontmatter_to_content(
    content: str,
    title: str = "",
    tags: list[str] | None = None,
    source: str = "",
    extra_fields: dict[str, Any] | None = None,
) -> str:
    """为 Markdown 内容添加 YAML front matter

    如果内容已存在 front matter，则更新它；否则添加新的。

    参数：
        content: 原始 Markdown 内容
        title: 文档标题（如未提供，尝试从内容中提取）
        tags: 标签列表
        source: 来源（URL或文件路径）
        extra_fields: 额外字段

    返回：
        添加了 front matter 的完整内容
    """
    existing_frontmatter, body = parse_yaml_frontmatter(content)

    if not title:
        title_match = re.match(r"^#\s+(.+)$", body.lstrip(), re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

    if tags is None:
        tags = []

    new_frontmatter = generate_yaml_frontmatter(title=title, tags=tags, source=source, extra_fields=extra_fields)

    return new_frontmatter + body


def add_yaml_frontmatter_to_file(
    file_path: str,
    title: str = "",
    tags: list[str] | None = None,
    source: str = "",
    extra_fields: dict[str, Any] | None = None,
) -> bool:
    """为 Markdown 文件添加 YAML front matter

    参数：
        file_path: Markdown 文件路径
        title: 文档标题
        tags: 标签列表
        source: 来源
        extra_fields: 额外字段

    返回：
        是否成功
    """
    p = Path(file_path)
    if not p.exists() or not p.suffix.lower() == ".md":
        return False

    try:
        content = p.read_text(encoding="utf-8")
        new_content = add_yaml_frontmatter_to_content(
            content, title=title, tags=tags, source=source, extra_fields=extra_fields
        )
        p.write_text(new_content, encoding="utf-8")
        return True
    except (OSError, ValueError) as e:
        logger.warning(f"[tag_extractor] add_yaml_frontmatter_to_file failed: {e}\n")
        return False


def process_and_tag_file_with_yaml(file_path: str, source: str = "", title: str = "") -> dict[str, Any]:
    """处理单个文件，基于文件名分词提取标签并添加 YAML front matter

    参数：
        file_path: Markdown 文件路径
        source: 来源信息（URL或原文件路径）
        title: 可选的标题覆盖

    返回：
        包含处理结果的字典：{'success': bool, 'tags': list, 'title': str}
    """
    result = {
        "success": False,
        "tags": [],
        "title": title,
    }

    p = Path(file_path)
    if not p.exists() or not p.suffix.lower() == ".md":
        return result

    try:
        content = p.read_text(encoding="utf-8")

        existing_frontmatter, body = parse_yaml_frontmatter(content)

        if not title:
            title = existing_frontmatter.get("title", "")
            if not title:
                from utils.helpers import extract_title_from_markdown

                title = extract_title_from_markdown(body) or p.stem

        tags = extract_tags_from_filename(file_path)

        new_frontmatter = generate_yaml_frontmatter(
            title=title,
            tags=tags,
            source=source,
        )

        new_content = new_frontmatter + body
        p.write_text(new_content, encoding="utf-8")

        result["success"] = True
        result["tags"] = tags
        result["title"] = title

        return result
    except (OSError, ValueError, UnicodeError) as e:
        logger.warning(f"[tag_extractor] process_and_tag_file_with_yaml failed: {e}\n")
        return result


def save_tags_md(workspace_path: str) -> dict:
    """Compatibility alias: the global tag database now lives in WIKI.md."""
    if not workspace_path:
        return {"success": False, "message": "未设置工作区"}

    workspace = Path(workspace_path)
    if not workspace.exists():
        return {"success": False, "message": "工作区不存在"}

    from utils.wiki_sync import sync_wiki_with_files

    result = sync_wiki_with_files()
    result["count"] = result.get("tags", 0)
    result["message"] = "标签索引已同步到 WIKI.md"
    return result
