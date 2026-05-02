import re
import json
import sys
from pathlib import Path
from config.settings import config

from utils.text_utils import tokenize as tokenize_text, _is_meaningful_tag, _normalize_for_match, _is_generic_word


def _get_pending_path():
    workspace = config.workspace_path
    if not workspace:
        return None
    return Path(workspace) / ".pending_topics.json"


def _get_wiki_path():
    workspace = config.workspace_path
    if not workspace:
        return None
    return Path(workspace) / "WIKI.md"


def load_pending():
    path = _get_pending_path()
    if not path or not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return []


def save_pending(pending):
    path = _get_pending_path()
    if not path:
        return
    path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding='utf-8')


def parse_wiki_headings():
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = Path(workspace) / "WIKI.md"
    if not wiki_path.exists():
        return []
    try:
        text = wiki_path.read_text(encoding='utf-8')
    except Exception:
        return []
    headings = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('## ') and not stripped.startswith('### '):
            headings.append({"level": 2, "name": stripped[3:].strip()})
        elif stripped.startswith('### '):
            headings.append({"level": 3, "name": stripped[4:].strip()})
    return headings


def parse_wiki_structure():
    """
    解析 WIKI.md 的主题结构，返回主题列表及其文件
    
    返回格式:
    [
        {
            "name": "主题名",
            "files": [
                {"title": "文件标题", "path": "相对路径"},
                ...
            ]
        },
        ...
    ]
    """
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = Path(workspace) / "WIKI.md"
    if not wiki_path.exists():
        return []
    try:
        text = wiki_path.read_text(encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[parse_wiki] read failed: {e}\n")
        sys.stderr.flush()
        return []

    topics = []
    lines = text.split('\n')

    current_topic = None
    in_source_files = False
    current_file = None

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*(.+?)\s*$')

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('## ') and not stripped.startswith('### '):
            if current_topic:
                if current_file:
                    if current_file.get('path'):
                        current_topic['files'].append(current_file)
                    current_file = None
                if current_topic['files']:
                    topics.append(current_topic)
                current_topic = None
                in_source_files = False

            topic_name = stripped[3:].strip()
            if topic_name and topic_name != '目录':
                current_topic = {"name": topic_name, "files": []}
                in_source_files = False
                current_file = None
            continue

        if stripped.startswith('### ') and current_topic:
            if stripped[4:].strip() == '来源文件':
                in_source_files = True
                if current_file:
                    if current_file.get('path'):
                        current_topic['files'].append(current_file)
                    current_file = None
            else:
                in_source_files = False
                if current_file:
                    if current_file.get('path'):
                        current_topic['files'].append(current_file)
                    current_file = None
            continue

        if in_source_files and current_topic:
            file_match = file_item_pattern.match(stripped)
            if file_match:
                if current_file:
                    if current_file.get('path'):
                        current_topic['files'].append(current_file)
                file_title = file_match.group(2).strip()
                current_file = {"title": file_title, "path": ""}
                continue

            if current_file:
                path_match = source_path_pattern.match(stripped)
                if path_match:
                    current_file['path'] = path_match.group(1).strip()

    if current_topic:
        if current_file:
            if current_file.get('path'):
                current_topic['files'].append(current_file)
        if current_topic['files']:
            topics.append(current_topic)

    return topics


def write_topic_to_file(file_path, topic):
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', text.lstrip('\ufeff'))
        if not m:
            return
        yaml_text = m.group(2)
        lines = yaml_text.split('\n')
        found = False
        for i, line in enumerate(lines):
            idx = line.find(':')
            if idx < 0:
                continue
            key = line[:idx].strip()
            if key == 'topic':
                lines[i] = f'topic: {topic}'
                found = True
                break
        if not found:
            lines.append(f'topic: {topic}')
        new_yaml = '\n'.join(lines)
        prefix = '\ufeff' if text.startswith('\ufeff') else ''
        new_text = prefix + m.group(1) + new_yaml + m.group(3) + text.lstrip('\ufeff')[m.end():]
        Path(file_path).write_text(new_text, encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[write_topic] failed: {e}\n")
        sys.stderr.flush()


def add_file_to_wiki_topic(file_rel_path, topic, file_title=None):
    """
    向 WIKI.md 添加文件到指定主题下
    
    格式:
    ## 主题名
    
    ### 来源文件
    
    1. **文件标题**
       - 文件名：xxx.md
       - 原始路径：Notes/xxx.md
    
    2. **文件标题2**
       - 文件名：xxx2.md
       - 原始路径：Notes/xxx2.md
    """
    wiki_path = _get_wiki_path()
    workspace = config.workspace_path
    if not wiki_path or not workspace:
        return False

    display_title = file_title or Path(file_rel_path).stem
    file_name = Path(file_rel_path).name

    try:
        if wiki_path.exists():
            content = wiki_path.read_text(encoding='utf-8')
        else:
            from datetime import datetime
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
    except Exception as e:
        sys.stderr.write(f"[wiki] read failed: {e}\n")
        sys.stderr.flush()
        return False

    lines = content.split('\n')
    topic_heading = f'## {topic}'

    topic_start_idx = None
    source_files_idx = None
    topic_end_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower() == topic_heading.lower():
            topic_start_idx = i
            source_files_idx = None
        elif topic_start_idx is not None and stripped == '### 来源文件':
            source_files_idx = i
        elif topic_start_idx is not None and stripped.startswith('## ') and not stripped.startswith('### '):
            topic_end_idx = i
            break

    if topic_end_idx is None and topic_start_idx is not None:
        topic_end_idx = len(lines)

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*`?(.+?)`?\s*$')

    if topic_start_idx is not None and source_files_idx is not None:
        max_index = 0
        for i in range(source_files_idx + 1, topic_end_idx):
            stripped = lines[i].strip()
            file_match = file_item_pattern.match(stripped)
            if file_match:
                idx = int(file_match.group(1))
                if idx > max_index:
                    max_index = idx
            path_match = source_path_pattern.match(stripped)
            if path_match and path_match.group(1).strip() == file_rel_path:
                return True

        next_index = max_index + 1

        insert_idx = topic_end_idx
        for i in range(source_files_idx + 1, topic_end_idx):
            stripped = lines[i].strip()
            file_match = file_item_pattern.match(stripped)
            if file_match:
                for j in range(i + 1, topic_end_idx):
                    next_stripped = lines[j].strip()
                    next_file_match = file_item_pattern.match(next_stripped)
                    if next_file_match:
                        insert_idx = j
                        break
                    if next_stripped.startswith('## '):
                        insert_idx = j
                        break
                if insert_idx == topic_end_idx:
                    insert_idx = topic_end_idx
                break

        new_lines = [
            f"{next_index}. **{display_title}**",
            f"   - 文件名：{file_name}",
            f"   - 原始路径：{file_rel_path}"
        ]

        for i, line in enumerate(new_lines):
            lines.insert(insert_idx + i, line)

    elif topic_start_idx is not None:
        insert_lines = [
            '',
            '### 来源文件',
            '',
            f"1. **{display_title}**",
            f"   - 文件名：{file_name}",
            f"   - 原始路径：{file_rel_path}"
        ]
        for i, line in enumerate(insert_lines):
            lines.insert(topic_end_idx + i, line)

    else:
        new_lines = [
            '',
            f'## {topic}',
            '',
            '### 来源文件',
            '',
            f"1. **{display_title}**",
            f"   - 文件名：{file_name}",
            f"   - 原始路径：{file_rel_path}"
        ]
        lines.extend(new_lines)

    try:
        new_content = '\n'.join(lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
        return True
    except Exception as e:
        sys.stderr.write(f"[wiki] write failed: {e}\n")
        sys.stderr.flush()
        return False


def _check_topic_needs_processing(yaml_text: str) -> bool:
    """
    检查文件的 topic 状态是否需要处理
    返回 True 如果：
    - 没有 topic 标签
    - 或 topic 标签为空
    - 或 topic 标签不唯一（列表形式有多个值）
    """
    has_topic = False
    topic_value = None
    
    for line in yaml_text.split('\n'):
        idx = line.find(':')
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1:].strip()
        if key == 'topic':
            has_topic = True
            topic_value = val
            break
    
    if not has_topic:
        return True
    
    if not topic_value or topic_value.strip() == '':
        return True
    
    if topic_value.startswith('[') and topic_value.endswith(']'):
        items = [t.strip().strip("'\"") for t in topic_value[1:-1].split(',') if t.strip()]
        if len(items) > 1:
            return True
        if len(items) == 0:
            return True
    
    return False


def _has_consecutive_two_words_match(topic_tokens: list, filename: str) -> bool:
    """
    第一优先级匹配：主题分词后是否有连续的两个词在文件名中出现（忽略空格）
    例如：主题["机器", "学习", "基础"] → 检查"机器学习"、"学习基础"是否在文件名中
    """
    filename_norm = _normalize_for_match(filename)

    for i in range(len(topic_tokens) - 1):
        word1 = topic_tokens[i]
        word2 = topic_tokens[i + 1]
        combined = _normalize_for_match(word1 + word2)
        if combined in filename_norm:
            return True

    return False




def _has_meaningful_word_match(word: str, topic_name: str) -> bool:
    """
    检查单词是否足够有意义且在主题名中出现（忽略空格）
    """
    if not _is_meaningful_tag(word):
        return False

    return _normalize_for_match(word) in _normalize_for_match(topic_name)


def _extract_topic_from_filename(filename: str, tags: list) -> str | None:
    """从文件名中提取主题名，不依赖 LLM。

    算法：从左到右取连续 meaningful token，跳过泛词，
    累积到 4+ 汉字或 2+ 英文词时停止，拼接作为主题名。
    文件名不足以构成主题时，回退到第一个 meaningful tag。
    """
    tokens = tokenize_text(filename)
    if not tokens:
        return None

    kept = []
    chinese_char_count = 0
    english_word_count = 0

    for t in tokens:
        if not _is_meaningful_tag(t) or _is_generic_word(t):
            continue
        kept.append(t)
        cn = len(re.findall(r'[一-鿿]', t))
        if cn > 0:
            chinese_char_count += cn
        else:
            english_word_count += 1
        if chinese_char_count >= 4 or english_word_count >= 2:
            return ''.join(kept)

    if kept:
        partial = ''.join(kept)
        for tag in tags:
            if _is_meaningful_tag(tag) and not _is_generic_word(tag) and tag.lower() != partial.lower():
                return partial + tag
        return partial

    for tag in tags:
        if _is_meaningful_tag(tag) and not _is_generic_word(tag):
            return tag

    return None


def auto_assign_topic_for_file(file_path):
    workspace = config.workspace_path
    if not workspace:
        return

    full_path = Path(file_path)
    if not full_path.exists():
        return

    try:
        text = full_path.read_text(encoding='utf-8')
    except Exception:
        return

    m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
    if not m:
        return

    yaml_text = m.group(1)
    tags = []
    title = full_path.stem

    for line in yaml_text.split('\n'):
        idx = line.find(':')
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1:].strip()
        if key == 'tags' and val.startswith('[') and val.endswith(']'):
            tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
        elif key == 'title':
            title = val.strip().strip("'\"")

    if not _check_topic_needs_processing(yaml_text):
        return

    headings = parse_wiki_headings()
    if not headings:
        return

    filename = full_path.stem

    high_priority_candidates = []
    low_priority_candidates = []

    for h in headings:
        h_name = h["name"]
        topic_tokens = tokenize_text(h_name)

        if _has_consecutive_two_words_match(topic_tokens, filename):
            high_priority_candidates.append(h)
            continue

        for tag in tags:
            if _has_meaningful_word_match(tag, h_name):
                if h not in low_priority_candidates:
                    low_priority_candidates.append(h)
                break

        for token in topic_tokens:
            if _is_meaningful_tag(token) and _normalize_for_match(token) in _normalize_for_match(filename):
                if h not in low_priority_candidates and h not in high_priority_candidates:
                    low_priority_candidates.append(h)
                break

    if high_priority_candidates:
        candidates = [h["name"] for h in high_priority_candidates]
    elif low_priority_candidates:
        candidates = [h["name"] for h in low_priority_candidates]
    else:
        topic_name = _extract_topic_from_filename(filename, tags)
        if topic_name:
            candidates = [topic_name]
        else:
            return

    if not candidates:
        return

    if len(candidates) == 1:
        write_topic_to_file(str(full_path), candidates[0])
        rel = str(full_path.relative_to(workspace)) if full_path.is_relative_to(workspace) else str(full_path)
        add_file_to_wiki_topic(rel, candidates[0], title)
        return

    pending = load_pending()
    rel = str(full_path.relative_to(workspace)) if full_path.is_relative_to(workspace) else str(full_path)
    pending.append({
        "file": rel,
        "title": title,
        "tags": tags,
        "candidates": candidates,
        "source": "wiki"
    })
    save_pending(pending)


def rename_wiki_topic(old_topic, new_topic):
    """
    重命名 WIKI.md 中的主题（包括标题和目录）
    
    返回: (success, updated_file_paths)
    - updated_file_paths: 该主题下所有文件的相对路径列表（用于后续更新 YAML）
    """
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return False, []

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[rename_topic] read failed: {e}\n")
        sys.stderr.flush()
        return False, []

    lines = content.split('\n')
    new_lines = []
    in_target_topic = False
    target_ended = False
    file_paths = []

    old_heading = f'## {old_topic}'
    new_heading = f'## {new_topic}'

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*(.+?)\s*$')

    current_file_has_path = False

    for line in lines:
        stripped = line.strip()

        if stripped == old_heading:
            in_target_topic = True
            target_ended = False
            new_lines.append(new_heading)
            continue

        if in_target_topic and not target_ended:
            if stripped.startswith('## ') and not stripped.startswith('### '):
                target_ended = True
                new_lines.append(line)
                continue

            file_match = file_item_pattern.match(stripped)
            if file_match:
                current_file_has_path = False

            path_match = source_path_pattern.match(stripped)
            if path_match:
                file_paths.append(path_match.group(1).strip())
                current_file_has_path = True

        new_lines.append(line)

    toc_line = None
    toc_start_idx = -1
    toc_end_idx = -1

    for i, line in enumerate(new_lines):
        stripped = line.strip()
        if stripped == '## 目录':
            toc_start_idx = i
            toc_end_idx = len(new_lines)
            for j in range(i + 1, len(new_lines)):
                if new_lines[j].strip().startswith('## ') and not new_lines[j].strip().startswith('### '):
                    toc_end_idx = j
                    break
            break

    if toc_start_idx >= 0:
        for i in range(toc_start_idx, toc_end_idx):
            stripped = new_lines[i].strip()
            if stripped.startswith('- [') and f'](#' in stripped:
                if f'](#{old_topic}' in stripped:
                    link_name = stripped[3:stripped.find(']')]
                    if link_name == old_topic:
                        new_lines[i] = f'- [{new_topic}](#{new_topic})'
                    break

    try:
        new_content = '\n'.join(new_lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
        return True, file_paths
    except Exception as e:
        sys.stderr.write(f"[rename_topic] write failed: {e}\n")
        sys.stderr.flush()
        return False, []


def rename_topic(old_topic, new_topic):
    """
    重命名主题：
    1. 重命名 WIKI.md 中的主题标题和目录链接
    2. 更新该主题下所有文件的 YAML topic 字段
    
    返回: {"success": bool, "message": str, "updated": int}
    """
    if not old_topic or not new_topic:
        return {"success": False, "message": "主题名不能为空"}

    if old_topic == new_topic:
        return {"success": True, "message": "主题名相同，无需修改", "updated": 0}

    wiki_success, file_paths = rename_wiki_topic(old_topic, new_topic)

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    workspace_path = Path(workspace)

    updated_count = 0
    for rel_path in file_paths:
        full_path = workspace_path / rel_path
        if full_path.exists():
            try:
                write_topic_to_file(str(full_path), new_topic)
                updated_count += 1
            except Exception as e:
                sys.stderr.write(f"[rename_topic] update YAML failed: {rel_path} - {e}\n")
                sys.stderr.flush()

    if not wiki_success and updated_count == 0:
        return {"success": False, "message": "重命名失败"}

    return {
        "success": True,
        "message": f"已重命名主题，更新 {updated_count} 个文件",
        "updated": updated_count
    }


def remove_file_from_wiki_topic(file_rel_path):
    """
    从 WIKI.md 中移除指定文件的记录（保留序号连续性）
    
    返回: (success, old_topic_name)
    - old_topic_name: 文件原来所在的主题名（如果找到）
    """
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return False, None

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[remove_file] read failed: {e}\n")
        sys.stderr.flush()
        return False, None

    lines = content.split('\n')
    new_lines = []

    current_topic = None
    in_source_files = False
    current_file_index = None
    current_file_contains_target = False
    file_item_buffer = []
    skip_count = 0
    old_topic = None

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*(.+?)\s*$')

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('## ') and not stripped.startswith('### '):
            if file_item_buffer:
                for buf_line in file_item_buffer:
                    new_lines.append(buf_line)
                file_item_buffer = []

            current_topic = stripped[3:].strip()
            in_source_files = False
            current_file_index = None
            current_file_contains_target = False
            skip_count = 0
            new_lines.append(line)
            continue

        if stripped == '### 来源文件':
            if file_item_buffer:
                for buf_line in file_item_buffer:
                    new_lines.append(buf_line)
                file_item_buffer = []

            in_source_files = True
            current_file_index = None
            current_file_contains_target = False
            skip_count = 0
            new_lines.append(line)
            continue

        if in_source_files and current_topic:
            file_match = file_item_pattern.match(stripped)
            if file_match:
                if file_item_buffer:
                    if current_file_contains_target:
                        old_topic = current_topic
                        skip_count += 1
                    else:
                        for buf_line in file_item_buffer:
                            new_lines.append(buf_line)
                    file_item_buffer = []

                current_file_index = int(file_match.group(1))
                current_file_contains_target = False
                file_item_buffer.append(line)
                continue

            path_match = source_path_pattern.match(stripped)
            if path_match and path_match.group(1).strip() == file_rel_path:
                current_file_contains_target = True
                if file_item_buffer:
                    file_item_buffer.append(line)
                continue

            if file_item_buffer:
                file_item_buffer.append(line)
                continue

        new_lines.append(line)

    if file_item_buffer:
        if current_file_contains_target:
            old_topic = current_topic
            skip_count += 1
        else:
            for buf_line in file_item_buffer:
                new_lines.append(buf_line)

    if skip_count > 0:
        def _renumber_lines(lines_list):
            result = []
            file_item_pattern_inner = re.compile(r'^(\s*)(\d+)\.\s+\*\*(.+?)\*\*\s*$')

            current_number = 0
            buffer = []
            in_section = False

            for line in lines_list:
                stripped = line.strip()
                if stripped == '### 来源文件':
                    in_section = True
                    current_number = 0
                    result.append(line)
                    continue

                if in_section:
                    if stripped.startswith('## ') and not stripped.startswith('### '):
                        in_section = False
                        if buffer:
                            for buf_line in buffer:
                                result.append(buf_line)
                            buffer = []
                        result.append(line)
                        continue

                    file_match_inner = file_item_pattern_inner.match(line)
                    if file_match_inner:
                        if buffer:
                            for buf_line in buffer:
                                result.append(buf_line)
                            buffer = []

                        current_number += 1
                        indent = file_match_inner.group(1)
                        title = file_match_inner.group(3)
                        new_line = f"{indent}{current_number}. **{title}**"
                        buffer.append(new_line)
                        continue

                    if buffer:
                        buffer.append(line)
                        continue

                result.append(line)

            if buffer:
                for buf_line in buffer:
                    result.append(buf_line)

            return result

        new_lines = _renumber_lines(new_lines)

    try:
        new_content = '\n'.join(new_lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
        return True, old_topic
    except Exception as e:
        sys.stderr.write(f"[remove_file] write failed: {e}\n")
        sys.stderr.flush()
        return False, None


def move_file_to_topic(file_rel_path, new_topic, file_title=None):
    """
    移动文件到新主题：
    1. 从原主题的 WIKI.md 中移除文件记录
    2. 将文件添加到新主题的 WIKI.md
    3. 更新文件 YAML 的 topic 字段
    
    返回: {"success": bool, "message": str}
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    file_path = Path(workspace) / file_rel_path
    if not file_path.exists():
        return {"success": False, "message": f"文件不存在: {file_rel_path}"}

    if file_title is None:
        try:
            text = file_path.read_text(encoding='utf-8')
            m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
            if m:
                yaml_text = m.group(1)
                for line in yaml_text.split('\n'):
                    idx = line.find(':')
                    if idx >= 0:
                        key = line[:idx].strip()
                        if key == 'title':
                            file_title = line[idx + 1:].strip().strip("'\"")
                            break
            if file_title is None:
                file_title = file_path.stem
        except Exception:
            file_title = file_path.stem

    remove_success, old_topic = remove_file_from_wiki_topic(file_rel_path)

    add_success = add_file_to_wiki_topic(file_rel_path, new_topic, file_title)

    write_topic_to_file(str(file_path), new_topic)

    if add_success:
        if old_topic:
            return {"success": True, "message": f"已从「{old_topic}」移动到「{new_topic}」"}
        else:
            return {"success": True, "message": f"已添加到「{new_topic}」"}
    else:
        return {"success": False, "message": "移动失败"}


def create_topic(topic_name):
    """
    在 WIKI.md 中创建新的主题条目
    
    格式:
    ## 主题名
    
    ### 来源文件
    
    """
    wiki_path = _get_wiki_path()
    workspace = config.workspace_path
    
    if not wiki_path or not workspace:
        return {"success": False, "message": "未设置工作区"}
    
    if not topic_name or not topic_name.strip():
        return {"success": False, "message": "主题名不能为空"}
    
    topic_name = topic_name.strip()
    
    try:
        if wiki_path.exists():
            content = wiki_path.read_text(encoding='utf-8')
        else:
            from datetime import datetime
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
        
        headings = parse_wiki_headings()
        for h in headings:
            if h["name"].lower() == topic_name.lower():
                return {"success": False, "message": f"主题「{topic_name}」已存在"}
        
        new_topic_lines = [
            "",
            f"## {topic_name}",
            "",
            "### 来源文件",
            "",
        ]
        
        lines = content.split('\n')
        
        insert_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip()
            if stripped.startswith('## ') and not stripped.startswith('### '):
                if stripped[3:].strip() != '目录':
                    insert_idx = i + 1
                    while insert_idx < len(lines):
                        next_stripped = lines[insert_idx].strip()
                        if next_stripped.startswith('## ') and not next_stripped.startswith('### '):
                            break
                        insert_idx += 1
                    break
        
        new_lines = lines[:insert_idx] + new_topic_lines + lines[insert_idx:]
        new_content = '\n'.join(new_lines)
        
        wiki_path.write_text(new_content, encoding='utf-8')
        
        return {"success": True, "message": f"主题「{topic_name}」创建成功"}
        
    except Exception as e:
        sys.stderr.write(f"[create_topic] failed: {e}\n")
        sys.stderr.flush()
        return {"success": False, "message": f"创建失败: {e}"}
