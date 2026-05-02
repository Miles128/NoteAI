import re
import math
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

from config import is_ignored_dir
from utils.text_utils import (
    is_chinese_word,
    is_english_word,
    tokenize_filename,
    CHINESE_STOPWORDS,
    OCCURRENCE_THRESHOLD,
    _count_tag_occurrence,
    _normalize_for_match,
    _is_generic_word,
)

try:
    import yaml
    PYYAML_AVAILABLE = True
except ImportError:
    yaml = None
    PYYAML_AVAILABLE = False


def _collect_workspace_md_filenames(workspace_path: str) -> List[str]:
    """收集 Notes、Organized、Used 文件夹中所有 MD 文件的文件名（只读文件名，不读内容）
    
    Args:
        workspace_path: 工作区根路径
    
    Returns:
        所有 md 文件的文件名列表（不含路径）
    """
    workspace = Path(workspace_path)
    filenames = []
    
    for folder_name in ['Notes', 'Organized', 'Used']:
        folder = workspace / folder_name
        if not folder.exists():
            continue
        md_files = [f for f in folder.rglob('*.md') if not f.name.startswith('.')]
        for md_file in md_files:
            filenames.append(md_file.name)
    
    return filenames


def _generate_english_pairs(english_words: List[str]) -> List[str]:
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


def _is_word_in_accepted_pair(word: str, accepted_pairs: List[str], case_insensitive: bool = True) -> bool:
    """检查单词是否已被包含在已接受的双词组合中（忽略空格）

    例如: "Machine" 在 "MachineLearning" 或 "Machine Learning" 中则返回 True
    """
    word_norm = _normalize_for_match(word)
    for pair in accepted_pairs:
        if word_norm in _normalize_for_match(pair):
            return True
    return False


def extract_tags_from_filename(file_path: str) -> List[str]:
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
    from config.settings import config
    
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


def tag_files_by_filename(file_paths: List[str]) -> Dict[str, List[str]]:
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
            sys.stderr.write(f"[tag_files_by_filename] 处理失败 {fp}: {e}\n")
            sys.stderr.flush()
    
    return results


def _parse_yaml_value_simple(value: str) -> Any:
    """简单的 YAML 值解析器（fallback，用于没有 PyYAML 时）"""
    value = value.strip()
    
    if not value:
        return None
    
    if value.startswith('[') and value.endswith(']'):
        list_content = value[1:-1].strip()
        if not list_content:
            return []
        items = []
        current = ""
        in_quotes = None
        i = 0
        while i < len(list_content):
            c = list_content[i]
            if c in ['"', "'"]:
                if in_quotes == c:
                    in_quotes = None
                elif in_quotes is None:
                    in_quotes = c
                else:
                    current += c
            elif c == ',' and in_quotes is None:
                items.append(current.strip())
                current = ""
            else:
                current += c
            i += 1
        if current:
            items.append(current.strip())
        result = []
        for item in items:
            item = item.strip()
            if item.startswith('"') and item.endswith('"'):
                item = item[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            elif item.startswith("'") and item.endswith("'"):
                item = item[1:-1].replace("\\'", "'").replace('\\\\', '\\')
            result.append(item)
        return result
    
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("\\'", "'").replace('\\\\', '\\')
    
    if value.lower() == 'true':
        return True
    if value.lower() == 'false':
        return False
    if value.lower() == 'null':
        return None
    
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    
    return value


def _parse_yaml_frontmatter_simple(content: str) -> Dict[str, Any]:
    """简单的 YAML front matter 解析器（fallback）"""
    result = {}
    lines = content.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            if key:
                result[key] = _parse_yaml_value_simple(value)
    
    return result


def _escape_yaml_string(value: str) -> str:
    """转义YAML字符串中的特殊字符"""
    if not value:
        return '""'
    
    needs_quoting = False
    special_chars = ['"', '\\', '\n', '\r', '\t', '#', ': ', '[', ']', '{', '}', ',', '*', '&', '!', '|', '>', '%', '@', '`']
    
    for char in special_chars:
        if char in value:
            needs_quoting = True
            break
    
    if value.startswith((' ', '-', '?', ':')) or value.endswith(' '):
        needs_quoting = True
    
    if not needs_quoting:
        return value
    
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\t', '\\t')
    
    return f'"{value}"'


def _format_yaml_value(value: Any) -> str:
    """格式化YAML值，根据类型选择合适的表示方式"""
    if value is None:
        return 'null'
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        if not value:
            return '[]'
        items = ', '.join(_escape_yaml_string(str(item)) for item in value)
        return f'[{items}]'
    elif isinstance(value, datetime):
        return _escape_yaml_string(value.strftime('%Y-%m-%d'))
    else:
        return _escape_yaml_string(str(value))


def generate_yaml_frontmatter(
    title: str = "",
    tags: List[str] = None,
    date: datetime = None,
    source: str = "",
    extra_fields: Dict[str, Any] = None
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
    fields = {}
    
    if title:
        fields['title'] = title
    
    if tags:
        fields['tags'] = tags
    else:
        fields['tags'] = []
    
    if date is None:
        date = datetime.now()
    fields['date'] = date
    
    if source:
        fields['source'] = source
    
    if extra_fields:
        fields.update(extra_fields)
    
    lines = ['---']
    
    ordered_keys = ['title', 'tags', 'date', 'source']
    for key in ordered_keys:
        if key in fields:
            value = fields.pop(key)
            lines.append(f"{key}: {_format_yaml_value(value)}")
    
    for key, value in sorted(fields.items()):
        lines.append(f"{key}: {_format_yaml_value(value)}")
    
    lines.append('---')
    lines.append('')
    
    return '\n'.join(lines)


def parse_yaml_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """解析 Markdown 文件中的 YAML front matter
    
    参数：
        content: Markdown 文件完整内容
    
    返回：
        (frontmatter_dict, remaining_content)
    """
    frontmatter = {}
    body = content
    
    if not content.startswith('---\n'):
        return frontmatter, body
    
    lines = content.split('\n')
    frontmatter_lines = []
    frontmatter_end_index = None
    
    for i, line in enumerate(lines[1:], start=1):
        if line == '---':
            frontmatter_end_index = i
            break
        frontmatter_lines.append(line)
    
    if frontmatter_end_index is None:
        return frontmatter, body
    
    frontmatter_content = '\n'.join(frontmatter_lines)
    if frontmatter_content.strip():
        try:
            if PYYAML_AVAILABLE and yaml is not None:
                frontmatter = yaml.safe_load(frontmatter_content) or {}
            else:
                frontmatter = _parse_yaml_frontmatter_simple(frontmatter_content)
        except Exception:
            frontmatter = {}
    
    remaining_lines = lines[frontmatter_end_index + 1:]
    while remaining_lines and remaining_lines[0].strip() == '':
        remaining_lines.pop(0)
    body = '\n'.join(remaining_lines)
    
    return frontmatter, body


def add_yaml_frontmatter_to_content(
    content: str,
    title: str = "",
    tags: List[str] = None,
    source: str = "",
    extra_fields: Dict[str, Any] = None
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
        title_match = re.match(r'^#\s+(.+)$', body.lstrip(), re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
    
    if tags is None:
        tags = []
    
    new_frontmatter = generate_yaml_frontmatter(
        title=title,
        tags=tags,
        source=source,
        extra_fields=extra_fields
    )
    
    return new_frontmatter + body


def add_yaml_frontmatter_to_file(
    file_path: str,
    title: str = "",
    tags: List[str] = None,
    source: str = "",
    extra_fields: Dict[str, Any] = None
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
    if not p.exists() or not p.suffix.lower() == '.md':
        return False
    
    try:
        content = p.read_text(encoding='utf-8')
        new_content = add_yaml_frontmatter_to_content(
            content,
            title=title,
            tags=tags,
            source=source,
            extra_fields=extra_fields
        )
        p.write_text(new_content, encoding='utf-8')
        return True
    except Exception:
        return False


def process_and_tag_file_with_yaml(
    file_path: str,
    source: str = "",
    title: str = ""
) -> Dict[str, Any]:
    """处理单个文件，基于文件名分词提取标签并添加 YAML front matter
    
    参数：
        file_path: Markdown 文件路径
        source: 来源信息（URL或原文件路径）
        title: 可选的标题覆盖
    
    返回：
        包含处理结果的字典：{'success': bool, 'tags': list, 'title': str}
    """
    result = {
        'success': False,
        'tags': [],
        'title': title,
    }
    
    p = Path(file_path)
    if not p.exists() or not p.suffix.lower() == '.md':
        return result
    
    try:
        content = p.read_text(encoding='utf-8')
        
        existing_frontmatter, body = parse_yaml_frontmatter(content)
        
        if not title:
            title = existing_frontmatter.get('title', '')
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
        p.write_text(new_content, encoding='utf-8')
        
        result['success'] = True
        result['tags'] = tags
        result['title'] = title
        
        return result
    except Exception:
        return result


def save_tags_md(workspace_path: str) -> dict:
    if not workspace_path:
        return {"success": False, "message": "未设置工作区"}

    workspace = Path(workspace_path)
    if not workspace.exists():
        return {"success": False, "message": "工作区不存在"}

    tag_map = {}

    def _scan(path):
        try:
            for entry in sorted(Path(path).iterdir(), key=lambda p: p.name.lower()):
                if entry.name.startswith('.'):
                    continue
                if entry.is_dir():
                    if is_ignored_dir(entry.name):
                        continue
                    _scan(str(entry))
                elif entry.suffix.lower() == '.md' and entry.name.lower() != 'wiki.md' and entry.name.lower() != 'tags.md':
                    try:
                        text = entry.read_text(encoding='utf-8')
                        m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
                        if not m:
                            continue
                        yaml_text = m.group(1)
                        rel = str(entry.relative_to(workspace))
                        current_tags_key = False
                        current_tags_arr = []
                        for line in yaml_text.split('\n'):
                            stripped = line.strip()
                            if current_tags_key and stripped.startswith('- '):
                                current_tags_arr.append(stripped[2:].strip().strip("'\""))
                                continue
                            if current_tags_key and current_tags_arr:
                                for tag in current_tags_arr:
                                    if tag not in tag_map:
                                        tag_map[tag] = []
                                    tag_map[tag].append(rel)
                                current_tags_key = False
                                current_tags_arr = []
                            idx = line.find(':')
                            if idx < 0:
                                continue
                            key = line[:idx].strip()
                            val = line[idx + 1:].strip()
                            if key != 'tags':
                                current_tags_key = False
                                continue
                            if val.startswith('[') and val.endswith(']'):
                                tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
                                for tag in tags:
                                    if tag not in tag_map:
                                        tag_map[tag] = []
                                    tag_map[tag].append(rel)
                                current_tags_key = False
                            elif not val:
                                current_tags_key = True
                                current_tags_arr = []
                            else:
                                tag = val.strip().strip("'\"")
                                if tag:
                                    if tag not in tag_map:
                                        tag_map[tag] = []
                                    tag_map[tag].append(rel)
                                current_tags_key = False
                        if current_tags_key and current_tags_arr:
                            for tag in current_tags_arr:
                                if tag not in tag_map:
                                    tag_map[tag] = []
                                tag_map[tag].append(rel)
                    except Exception:
                        # YAML front matter parse failure on individual file, non-critical
                        pass
        except PermissionError:
            pass

    _scan(str(workspace))

    lines = ['# Tags', '']
    sorted_tags = sorted(tag_map.items(), key=lambda x: -len(x[1]))
    for tag, files in sorted_tags:
        lines.append('## ' + tag)
        lines.append('')
        for f in files:
            fname = Path(f).stem
            lines.append('- [[' + fname + ']]')
        lines.append('')

    tags_md_path = workspace / 'tags.md'
    tags_md_path.write_text('\n'.join(lines), encoding='utf-8')

    return {"success": True, "count": len(sorted_tags)}
