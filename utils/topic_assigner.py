import re
import json
import sys
from pathlib import Path
from config.settings import config
from utils.logger import logger

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
    tmp_path = path.with_suffix('.tmp')
    tmp_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp_path.replace(path)


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
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*`?(.+?)`?\s*$')

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
                import yaml
                lines[i] = 'topic: ' + yaml.dump(topic, default_flow_style=True).strip()
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


def auto_assign_topic_for_file(file_path):
    workspace = config.workspace_path
    if not workspace:
        return None

    full_path = Path(file_path)
    if not full_path.exists():
        return None

    try:
        text = full_path.read_text(encoding='utf-8')
    except Exception:
        return None

    m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('\ufeff'))
    if not m:
        return None

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
        return None

    headings = parse_wiki_headings()
    filename = full_path.stem

    if not headings:
        pending = load_pending()
        rel = str(full_path.relative_to(workspace)) if full_path.is_relative_to(workspace) else str(full_path)
        pending.append({
            "file": rel,
            "title": title,
            "tags": tags,
            "candidates": [],
            "source": "none"
        })
        save_pending(pending)
        return {"status": "pending", "source": "none"}

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
    else:
        candidates = []

    extra_candidates = []
    for h in low_priority_candidates:
        if h["name"] not in candidates:
            extra_candidates.append(h["name"])

    for tag in tags:
        if _is_meaningful_tag(tag) and not _is_generic_word(tag):
            if tag not in candidates and tag not in extra_candidates:
                extra_candidates.append(tag)

    filename_tokens = tokenize_text(filename)
    for token in filename_tokens:
        if _is_meaningful_tag(token) and not _is_generic_word(token):
            if token not in candidates and token not in extra_candidates:
                extra_candidates.append(token)

    if high_priority_candidates and len(candidates) == 1 and not extra_candidates:
        write_topic_to_file(str(full_path), candidates[0])
        rel = str(full_path.relative_to(workspace)) if full_path.is_relative_to(workspace) else str(full_path)
        add_file_to_wiki_topic(rel, candidates[0], title)
        return {"status": "auto_assigned", "topic": candidates[0]}

    all_candidates = candidates + extra_candidates

    pending = load_pending()
    rel = str(full_path.relative_to(workspace)) if full_path.is_relative_to(workspace) else str(full_path)
    pending.append({
        "file": rel,
        "title": title,
        "tags": tags,
        "candidates": all_candidates,
        "source": "wiki" if high_priority_candidates else "low_priority"
    })
    save_pending(pending)
    return {"status": "pending", "source": "wiki" if high_priority_candidates else "low_priority"}


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
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*`?(.+?)`?\s*$')

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


def _remove_empty_topic_sections(topic_name_lower):
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return
    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception:
        return
    lines = content.split('\n')
    result_lines = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('## ') and not stripped.startswith('### '):
            heading_name = stripped[3:].strip()
            if heading_name.lower() == topic_name_lower:
                section_lines = [lines[i]]
                has_files = False
                j = i + 1
                while j < len(lines):
                    s = lines[j].strip()
                    if s.startswith('## ') and not s.startswith('### '):
                        break
                    section_lines.append(lines[j])
                    if s.startswith('- 原始路径') or s.startswith('- 原始路径：') or s.startswith('- 原始路径:'):
                        has_files = True
                    j += 1
                if has_files:
                    result_lines.extend(section_lines)
                i = j
                continue
        result_lines.append(lines[i])
        i += 1
    try:
        new_content = '\n'.join(result_lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
    except Exception as e:
        logger.warning(f"[topic_assigner] 写入 WIKI.md 失败: {e}")


def _merge_duplicate_topics_in_wiki():
    """
    直接操作 WIKI.md 文本，将所有同名（小写匹配）的主题段合并为第一个段。
    合并逻辑：
    1. 扫描 WIKI.md，按小写名称分组所有主题段
    2. 对有多个段的同名主题，将后续段的文件追加到第一个段，然后移除后续段
    3. 去重：同一文件路径只保留一次
    返回: 合并的重复主题数量
    """
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return 0

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception:
        return 0

    lines = content.split('\n')

    sections = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('## ') and not stripped.startswith('### '):
            heading_name = stripped[3:].strip()
            if heading_name == '目录':
                i += 1
                continue
            section_start = i
            section_lines = [lines[i]]
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if s.startswith('## ') and not s.startswith('### '):
                    break
                section_lines.append(lines[j])
                j += 1
            sections.append({
                "name": heading_name,
                "start": section_start,
                "end": j,
                "lines": section_lines
            })
            i = j
        else:
            i += 1

    name_groups = {}
    for sec in sections:
        key = sec["name"].lower()
        if key not in name_groups:
            name_groups[key] = []
        name_groups[key].append(sec)

    merged_count = 0
    sections_to_remove = []

    for key, group in name_groups.items():
        if len(group) <= 1:
            continue

        keeper = group[0]
        source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*`?(.+?)`?\s*$')
        file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')

        existing_paths = set()
        for line in keeper["lines"]:
            m = source_path_pattern.match(line.strip())
            if m:
                existing_paths.add(m.group(1).strip())

        new_file_entries = []
        for dup in group[1:]:
            current_title = None
            current_path = None
            for line in dup["lines"]:
                s = line.strip()
                fm = file_item_pattern.match(s)
                if fm:
                    current_title = fm.group(2).strip()
                    current_path = None
                pm = source_path_pattern.match(s)
                if pm:
                    current_path = pm.group(1).strip()
                    if current_path and current_path not in existing_paths:
                        existing_paths.add(current_path)
                        new_file_entries.append({
                            "title": current_title or Path(current_path).stem,
                            "path": current_path
                        })
            sections_to_remove.append(dup)

        if new_file_entries:
            max_index = 0
            for line in keeper["lines"]:
                fm = file_item_pattern.match(line.strip())
                if fm:
                    idx = int(fm.group(1))
                    if idx > max_index:
                        max_index = idx

            insert_pos = len(keeper["lines"])
            for k in range(len(keeper["lines"]) - 1, -1, -1):
                s = keeper["lines"][k].strip()
                pm = source_path_pattern.match(s)
                if pm:
                    insert_pos = k + 1
                    break

            new_lines = []
            for entry in new_file_entries:
                max_index += 1
                new_lines.append(f"{max_index}. **{entry['title']}**")
                new_lines.append(f"   - 文件名：{Path(entry['path']).name}")
                new_lines.append(f"   - 原始路径：{entry['path']}")

            keeper["lines"] = keeper["lines"][:insert_pos] + new_lines + keeper["lines"][insert_pos:]

        merged_count += len(group) - 1

    if merged_count == 0:
        return 0

    remove_ranges = set()
    for sec in sections_to_remove:
        for idx in range(sec["start"], sec["end"]):
            remove_ranges.add(idx)
    for key, group in name_groups.items():
        if len(group) > 1:
            keeper = group[0]
            for idx in range(keeper["start"], keeper["end"]):
                remove_ranges.add(idx)

    keeper_replacements = {}
    for key, group in name_groups.items():
        if len(group) > 1:
            keeper = group[0]
            keeper_replacements[keeper["start"]] = keeper["lines"]

    new_lines = []
    for i, line in enumerate(lines):
        if i in remove_ranges:
            if i in keeper_replacements:
                for sl in keeper_replacements[i]:
                    new_lines.append(sl)
            continue
        new_lines.append(line)

    try:
        new_content = '\n'.join(new_lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
    except Exception:
        pass

    return merged_count


def _deduplicate_files_in_wiki():
    """
    去除 WIKI.md 中每个主题段内的重复文件（按原始路径去重）
    返回: 去除的重复文件数量
    """
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return 0

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception:
        return 0

    lines = content.split('\n')
    result_lines = []
    i = 0
    removed_count = 0

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*`?(.+?)`?\s*$')

    while i < len(lines):
        stripped = lines[i].strip()

        if stripped.startswith('## ') and not stripped.startswith('### '):
            section_start = i
            section_lines = [lines[i]]
            seen_paths = set()
            j = i + 1
            current_file_lines = []
            current_path = None

            while j < len(lines):
                s = lines[j].strip()
                if s.startswith('## ') and not s.startswith('### '):
                    break

                fm = file_item_pattern.match(s)
                if fm:
                    if current_file_lines:
                        if current_path is None or current_path not in seen_paths:
                            if current_path:
                                seen_paths.add(current_path)
                            section_lines.extend(current_file_lines)
                        else:
                            removed_count += 1
                    current_file_lines = [lines[j]]
                    current_path = None
                elif current_file_lines:
                    current_file_lines.append(lines[j])
                    pm = source_path_pattern.match(s)
                    if pm:
                        current_path = pm.group(1).strip()
                else:
                    section_lines.append(lines[j])

                j += 1

            if current_file_lines:
                if current_path is None or current_path not in seen_paths:
                    if current_path:
                        seen_paths.add(current_path)
                    section_lines.extend(current_file_lines)
                else:
                    removed_count += 1

            idx = 1
            final_section = []
            for line in section_lines:
                fm = file_item_pattern.match(line.strip())
                if fm:
                    final_section.append(f"{idx}. **{fm.group(2)}**")
                    idx += 1
                else:
                    final_section.append(line)

            result_lines.extend(final_section)
            i = j
            continue

        result_lines.append(lines[i])
        i += 1

    if removed_count > 0:
        try:
            new_content = '\n'.join(result_lines)
            if not new_content.endswith('\n'):
                new_content += '\n'
            wiki_path.write_text(new_content, encoding='utf-8')
        except Exception:
            pass

    return removed_count


def _remove_topic_from_wiki(topic_name):
    """
    从 WIKI.md 中移除整个主题（包括标题和所有文件）
    返回: (success, removed_file_paths)
    """
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return False, []

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception as e:
        sys.stderr.write(f"[_remove_topic] read failed: {e}\n")
        sys.stderr.flush()
        return False, []

    lines = content.split('\n')
    new_lines = []
    in_target_topic = False
    target_ended = False
    removed_file_paths = []

    target_heading = f'## {topic_name}'

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*`?(.+?)`?\s*$')

    for line in lines:
        stripped = line.strip()

        if stripped == target_heading:
            in_target_topic = True
            target_ended = False
            continue

        if in_target_topic and not target_ended:
            if stripped.startswith('## ') and not stripped.startswith('### '):
                target_ended = True
                new_lines.append(line)
                continue

            path_match = source_path_pattern.match(stripped)
            if path_match:
                removed_file_paths.append(path_match.group(1).strip())
            continue

        new_lines.append(line)

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
        final_toc_lines = []
        for i in range(toc_start_idx, toc_end_idx):
            stripped = new_lines[i].strip()
            if stripped.startswith('- [') and f'](#' in stripped:
                if f'](#{topic_name}' in stripped:
                    link_name = stripped[3:stripped.find(']')]
                    if link_name == topic_name:
                        continue
            final_toc_lines.append(new_lines[i])

        new_lines = new_lines[:toc_start_idx] + final_toc_lines + new_lines[toc_end_idx:]

    try:
        new_content = '\n'.join(new_lines)
        if not new_content.endswith('\n'):
            new_content += '\n'
        wiki_path.write_text(new_content, encoding='utf-8')
        return True, removed_file_paths
    except Exception as e:
        sys.stderr.write(f"[_remove_topic] write failed: {e}\n")
        sys.stderr.flush()
        return False, removed_file_paths


def delete_topic(topic_name):
    """
    删除主题：
    1. 从 WIKI.md 中移除整个主题（标题+文件列表+目录链接）
    2. 清除该主题下所有文件的 YAML topic 字段
    3. 对每个文件重新尝试自动匹配主题
    4. 匹配不到的放入待确认列表

    返回: {"success": bool, "message": str, "reassigned": int, "pending": int}
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    wiki_structure = parse_wiki_structure()
    topic_data = None
    for t in wiki_structure:
        if t["name"] == topic_name:
            topic_data = t
            break

    if not topic_data:
        return {"success": False, "message": f"主题「{topic_name}」不存在"}

    file_paths = [f.get("path", "") for f in topic_data.get("files", []) if f.get("path")]

    wiki_ok, _ = _remove_topic_from_wiki(topic_name)
    if not wiki_ok:
        return {"success": False, "message": "从 WIKI.md 删除主题失败"}

    workspace_path = Path(workspace)

    for rel_path in file_paths:
        full_path = workspace_path / rel_path
        if full_path.exists():
            try:
                _clear_topic_in_file(str(full_path))
            except Exception as e:
                sys.stderr.write(f"[delete_topic] clear topic failed: {rel_path} - {e}\n")
                sys.stderr.flush()

    reassigned_count = 0
    pending_count = 0

    for rel_path in file_paths:
        full_path = workspace_path / rel_path
        if not full_path.exists():
            continue

        try:
            result = auto_assign_topic_for_file(str(full_path))
            if result:
                reassigned_count += 1
            else:
                pending_count += 1
        except Exception as e:
            sys.stderr.write(f"[delete_topic] reassign failed: {rel_path} - {e}\n")
            sys.stderr.flush()
            pending_count += 1

    return {
        "success": True,
        "message": f"已删除主题「{topic_name}」，重新分配 {reassigned_count} 个文件，{pending_count} 个待确认",
        "reassigned": reassigned_count,
        "pending": pending_count
    }


def _clear_topic_in_file(file_path):
    """清除文件 YAML 中的 topic 字段"""
    text = Path(file_path).read_text(encoding='utf-8')
    bom = '\ufeff' if text.startswith('\ufeff') else ''
    clean = text.lstrip('\ufeff')
    m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', clean)
    if not m:
        return

    yaml_text = m.group(2)
    lines = yaml_text.split('\n')
    new_lines = []
    for line in lines:
        idx = line.find(':')
        if idx >= 0:
            key = line[:idx].strip()
            if key == 'topic':
                continue
        new_lines.append(line)

    new_yaml = '\n'.join(new_lines)
    new_content = bom + m.group(1) + new_yaml + m.group(3) + clean[m.end():]
    Path(file_path).write_text(new_content, encoding='utf-8')


def rename_topic(old_topic, new_topic):
    """
    重命名主题：
    1. 检查新主题名是否已存在
    2. 如果存在：合并文件（旧主题文件移到新主题，更新 YAML，删除旧主题）
    3. 如果不存在：按原来的方案（重命名 WIKI.md 标题 + 更新 YAML）
    
    返回: {"success": bool, "message": str, "updated": int, "merged": bool}
    """
    if not old_topic or not new_topic:
        return {"success": False, "message": "主题名不能为空"}

    if old_topic == new_topic:
        return {"success": True, "message": "主题名相同，无需修改", "updated": 0, "merged": False}

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    workspace_path = Path(workspace)

    headings = parse_wiki_headings()
    new_topic_exists = False
    for h in headings:
        if h["name"].lower() == new_topic.lower():
            new_topic_exists = True
            new_topic = h["name"]
            break

    if new_topic_exists:
        wiki_structure = parse_wiki_structure()
        old_topic_data = None
        for t in wiki_structure:
            if t["name"] == old_topic:
                old_topic_data = t
                break

        if not old_topic_data:
            return {"success": False, "message": f"主题「{old_topic}」不存在", "updated": 0, "merged": False}

        old_file_paths = [f.get("path", "") for f in old_topic_data.get("files", []) if f.get("path")]

        for rel_path in old_file_paths:
            write_topic_to_file(str(workspace_path / rel_path), new_topic)

        for f in old_topic_data.get("files", []):
            file_path = f.get("path", "")
            file_title = f.get("title", "")
            if file_path:
                add_file_to_wiki_topic(file_path, new_topic, file_title)

        _remove_topic_from_wiki(old_topic)
        _merge_duplicate_topics_in_wiki()
        _deduplicate_files_in_wiki()

        return {
            "success": True,
            "message": f"已合并到「{new_topic}」，移动 {len(old_file_paths)} 个文件",
            "updated": len(old_file_paths),
            "merged": True
        }

    wiki_success, old_file_paths = rename_wiki_topic(old_topic, new_topic)

    updated_count = 0
    for rel_path in old_file_paths:
        full_path = workspace_path / rel_path
        if full_path.exists():
            try:
                write_topic_to_file(str(full_path), new_topic)
                updated_count += 1
            except Exception as e:
                sys.stderr.write(f"[rename_topic] update YAML failed: {rel_path} - {e}\n")
                sys.stderr.flush()

    if not wiki_success and updated_count == 0:
        return {"success": False, "message": "重命名失败", "merged": False}

    return {
        "success": True,
        "message": f"已重命名主题，更新 {updated_count} 个文件",
        "updated": updated_count,
        "merged": False
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
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*`?(.+?)`?\s*$')

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


def _read_topic_from_file(file_path):
    """
    从文件的 YAML frontmatter 中读取 topic 字段
    返回: topic 字符串（如果没有则返回 None）
    """
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', text.lstrip('\ufeff'))
        if not m:
            return None
        yaml_text = m.group(2)
        for line in yaml_text.split('\n'):
            idx = line.find(':')
            if idx < 0:
                continue
            key = line[:idx].strip()
            val = line[idx + 1:].strip()
            if key == 'topic':
                if val and val.strip():
                    return val.strip()
                return None
        return None
    except Exception as e:
        sys.stderr.write(f"[_read_topic] failed: {e}\n")
        sys.stderr.flush()
        return None


def _read_title_from_file(file_path):
    """
    从文件的 YAML frontmatter 中读取 title 字段
    返回: title 字符串（如果没有则返回文件名）
    """
    try:
        text = Path(file_path).read_text(encoding='utf-8')
        m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', text.lstrip('\ufeff'))
        if m:
            yaml_text = m.group(2)
            for line in yaml_text.split('\n'):
                idx = line.find(':')
                if idx < 0:
                    continue
                key = line[:idx].strip()
                val = line[idx + 1:].strip()
                if key == 'title':
                    if val and val.strip():
                        return val.strip().strip("'\"")
        return Path(file_path).stem
    except Exception:
        return Path(file_path).stem


def sync_wiki_with_files():
    """
    同步 WIKI.md 与文件的 YAML topic 标签：
    1. 扫描工作区所有 .md 文件，读取每个文件的 YAML topic
    2. 解析当前 WIKI.md 的结构
    3. 对比：以文件 YAML 中的 topic 为准
       - 如果文件在 WIKI 中位置与 YAML 不匹配 → 移动
       - 如果 YAML 中有 topic 但 WIKI 中没有该文件 → 添加
       - 如果文件在 WIKI 中但 YAML 没有 topic → 从 WIKI 移除
    4. 清理空主题（没有任何文件的主题）
    
    返回: {
        "success": bool,
        "message": str,
        "moved": int,    // 移动的文件数
        "added": int,    // 新增的文件数
        "removed": int,  // 从 WIKI 移除的文件数
        "deleted_topics": int  // 删除的空主题数
    }
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "moved": 0, "added": 0, "removed": 0, "deleted_topics": 0}

    workspace_path = Path(workspace)

    md_files = list(workspace_path.rglob('*.md'))
    wiki_path = workspace_path / "WIKI.md"

    file_topics = {}
    for md_file in md_files:
        if md_file.name == 'WIKI.md':
            continue
        try:
            rel_path = str(md_file.relative_to(workspace_path))
            topic = _read_topic_from_file(str(md_file))
            file_topics[rel_path] = topic
        except Exception:
            continue

    wiki_structure = parse_wiki_structure()

    wiki_file_to_topic = {}
    for topic in wiki_structure:
        topic_name = topic["name"]
        for f in topic["files"]:
            file_path = f.get("path", "")
            if file_path:
                wiki_file_to_topic[file_path] = topic_name

    moved_count = 0
    added_count = 0
    removed_count = 0

    for rel_path, yaml_topic in file_topics.items():
        wiki_topic = wiki_file_to_topic.get(rel_path)

        if yaml_topic is None:
            if wiki_topic is not None:
                remove_file_from_wiki_topic(rel_path)
                removed_count += 1
            continue

        if wiki_topic is None:
            file_title = _read_title_from_file(str(workspace_path / rel_path))
            headings = parse_wiki_headings()
            topic_exists = False
            for h in headings:
                if h["name"].lower() == yaml_topic.lower():
                    yaml_topic = h["name"]
                    topic_exists = True
                    break
            if not topic_exists:
                create_topic(yaml_topic)
            add_file_to_wiki_topic(rel_path, yaml_topic, file_title)
            added_count += 1
        elif wiki_topic.lower() != yaml_topic.lower():
            move_file_to_topic(rel_path, yaml_topic)
            moved_count += 1

    for rel_path in wiki_file_to_topic:
        if rel_path not in file_topics:
            remove_file_from_wiki_topic(rel_path)
            removed_count += 1

    merged_topic_count = _merge_duplicate_topics_in_wiki()

    dedup_count = _deduplicate_files_in_wiki()

    deleted_topic_count = 0
    while True:
        current_structure = parse_wiki_structure()
        deleted_any = False
        for topic in current_structure:
            if not topic["files"]:
                _remove_topic_from_wiki(topic["name"])
                deleted_topic_count += 1
                deleted_any = True
                break
        if not deleted_any:
            break

    return {
        "success": True,
        "message": f"同步完成：移动 {moved_count}，新增 {added_count}，移除 {removed_count}，合并重复主题 {merged_topic_count}，删除空主题 {deleted_topic_count}",
        "moved": moved_count,
        "added": added_count,
        "removed": removed_count,
        "merged_topics": merged_topic_count,
        "deleted_topics": deleted_topic_count
    }
