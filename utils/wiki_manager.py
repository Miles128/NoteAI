"""WIKI.md 管理模块 — 解析、读写、同步、去重、合并"""

import re
import sys
import shutil
from pathlib import Path
from datetime import datetime

from config.settings import config
from config.constants import TOPIC_SEP
from utils.logger import logger
from utils.text_utils import tokenize as tokenize_text, _is_meaningful_tag, _normalize_for_match, _is_generic_word

def _get_wiki_path():
    workspace = config.workspace_path
    if not workspace:
        return None
    ws = Path(workspace)
    new_path = ws / "wiki" / "WIKI.md"
    if new_path.exists():
        return new_path
    old_path = ws / "WIKI.md"
    if old_path.exists():
        return old_path
    return new_path


def parse_wiki_headings():
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = Path(workspace) / "wiki" / "WIKI.md"
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
    解析 WIKI.md 的主题结构，支持多级主题（用 / 分隔的路径）
    
    返回格式:
    [
        {
            "name": "主题路径",  # 例如 "人工智能/深度学习"
            "label": "深度学习",  # 最后一段名称
            "files": [...]
        },
        ...
    ]
    """
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = Path(workspace) / "wiki" / "WIKI.md"
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
    topic_stack = []

    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    source_path_pattern = re.compile(r'^\s*-\s*原始路径\s*[：:]\s*`?(.+?)`?\s*$')

    def _flush_topic():
        nonlocal current_topic, current_file
        if current_topic:
            if current_file:
                if current_file.get('path'):
                    current_topic['files'].append(current_file)
                current_file = None
            topics.append(current_topic)
            current_topic = None

    for line in lines:
        stripped = line.strip()

        heading_match = re.match(r'^(#{2,})\s+(.+)$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            if heading_text == '目录' or heading_text == '来源文件':
                if heading_text == '来源文件':
                    in_source_files = True
                    if current_file:
                        if current_file.get('path'):
                            current_topic['files'].append(current_file)
                        current_file = None
                else:
                    in_source_files = False
                continue

            _flush_topic()

            while len(topic_stack) >= level - 1:
                topic_stack.pop()

            parent_path = topic_stack[-1] if topic_stack else ''
            if parent_path:
                topic_path = parent_path + TOPIC_SEP + heading_text
            else:
                topic_path = heading_text

            topic_stack.append(topic_path)
            current_topic = {"name": topic_path, "label": heading_text, "files": []}
            in_source_files = False
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

    _flush_topic()

    return topics


def add_file_to_wiki_topic(file_rel_path, topic, file_title=None):
    """
    向 WIKI.md 添加文件到指定主题下
    支持多级主题路径（用 / 分隔），自动创建层级标题
    
    格式:
    ## 人工智能
    
    ### 深度学习
    
    #### Transformer
    1. **文件标题**
       - 原始路径：Notes/xxx.md
    """
    wiki_path = _get_wiki_path()
    workspace = config.workspace_path
    if not wiki_path or not workspace:
        return False

    if '/' in topic and TOPIC_SEP not in topic:
        topic = topic.replace('/', TOPIC_SEP)

    display_title = file_title or Path(file_rel_path).name
    file_name = Path(file_rel_path).name

    try:
        if wiki_path.exists():
            content = wiki_path.read_text(encoding='utf-8')
        else:
            wiki_path.parent.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
    except Exception as e:
        sys.stderr.write(f"[wiki] read failed: {e}\n")
        sys.stderr.flush()
        return False

    parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
    topic_leaf = parts[-1]
    topic_depth = len(parts)

    lines = content.split('\n')

    heading_prefix = '#' * (topic_depth + 1)
    topic_heading = f'{heading_prefix} {topic_leaf}'

    topic_start_idx = None
    source_files_idx = None
    topic_end_idx = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == topic_heading:
            topic_start_idx = i
            source_files_idx = None
        elif topic_start_idx is not None and stripped == '### 来源文件':
            source_files_idx = i
        elif topic_start_idx is not None and re.match(r'^#{2,}\s+', stripped):
            existing_level = len(re.match(r'^(#{2,})', stripped).group(1))
            if existing_level <= topic_depth + 1:
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
        last_file_item_idx = None
        for i in range(source_files_idx + 1, topic_end_idx):
            stripped = lines[i].strip()
            file_match = file_item_pattern.match(stripped)
            if file_match:
                last_file_item_idx = i
            elif re.match(r'^#{2,}\s+', stripped):
                break

        if last_file_item_idx is not None:
            insert_idx = last_file_item_idx + 1
            while insert_idx < topic_end_idx and source_path_pattern.match(lines[insert_idx].strip()):
                insert_idx += 1

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
        parent_insert_idx = len(lines)

        for pi in range(len(parts) - 1):
            parent_path = TOPIC_SEP.join(parts[:pi + 1])
            parent_label = parts[pi]
            parent_heading_prefix = '#' * (pi + 2)
            parent_heading = f'{parent_heading_prefix} {parent_label}'

            parent_found = False
            for i, line in enumerate(lines):
                if line.strip() == parent_heading:
                    parent_found = True
                    parent_insert_idx = i + 1
                    while parent_insert_idx < len(lines):
                        next_stripped = lines[parent_insert_idx].strip()
                        next_heading_match = re.match(r'^(#{2,})\s+', next_stripped)
                        if next_heading_match:
                            next_level = len(next_heading_match.group(1))
                            if next_level <= pi + 2:
                                break
                        parent_insert_idx += 1
                    break

            if not parent_found:
                new_section = [
                    '',
                    parent_heading,
                    ''
                ]
                for i, l in enumerate(new_section):
                    lines.insert(parent_insert_idx + i, l)
                parent_insert_idx += len(new_section)

        new_lines = [
            '',
            topic_heading,
            '',
            '### 来源文件',
            '',
            f"1. **{display_title}**",
            f"   - 文件名：{file_name}",
            f"   - 原始路径：{file_rel_path}"
        ]
        for i, l in enumerate(new_lines):
            lines.insert(parent_insert_idx + i, l)

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

        workspace = config.workspace_path
        if workspace:
            import shutil
            old_dir = Path(workspace) / config.NOTES_FOLDER / old_topic
            new_dir = Path(workspace) / config.NOTES_FOLDER / new_topic
            if old_dir.exists() and old_dir.is_dir():
                if new_dir.exists():
                    for item in old_dir.iterdir():
                        dst = new_dir / item.name
                        if dst.exists():
                            if item.is_dir():
                                shutil.rmtree(str(dst))
                            else:
                                dst.unlink()
                        shutil.move(str(item), str(dst))
                    shutil.rmtree(str(old_dir))
                else:
                    old_dir.rename(new_dir)

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
    except Exception as e:
        sys.stderr.write(f"[_merge_topics] write failed: {e}\n"); sys.stderr.flush()

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
        except Exception as e:
            sys.stderr.write(f"[_deduplicate_files] write failed: {e}\n"); sys.stderr.flush()

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
    1. 将主题文件夹下所有文件移动到 Notes 根目录
    2. 从 WIKI.md 中移除整个主题
    3. 清除文件的 YAML topic 字段，等待重新分配
    4. 清理空的主题文件夹和综述文件

    返回: {"success": bool, "message": str, "reassigned": int, "pending": int}
    """
    import shutil

    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    workspace_path = Path(workspace)
    notes_dir = workspace_path / config.NOTES_FOLDER
    parts = [p.strip() for p in topic_name.split(TOPIC_SEP) if p.strip()]
    notes_topic_dir = notes_dir
    for part in parts:
        notes_topic_dir = notes_topic_dir / part
    organized_topic_dir = workspace_path / config.ABSTRACT_FOLDER
    for part in parts:
        organized_topic_dir = organized_topic_dir / part

    # Collect all actual files from the topic directory
    actual_files = []
    if notes_topic_dir.exists() and notes_topic_dir.is_dir():
        for f in notes_topic_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() == ".md":
                actual_files.append(f)

    # Also collect from WIKI.md for cleanup reference
    wiki_structure = parse_wiki_structure()
    wiki_file_paths = []
    for t in wiki_structure:
        if t["name"] == topic_name:
            wiki_file_paths = [f.get("path", "") for f in t.get("files", []) if f.get("path")]
            break

    # 1. Move all files from topic folder to Notes root
    notes_root = notes_dir
    notes_root.mkdir(parents=True, exist_ok=True)
    moved_count = 0
    for src in actual_files:
        dst = notes_root / src.name
        # Handle name conflicts: append _1, _2 etc.
        if dst.exists():
            stem = src.stem
            suffix = src.suffix
            counter = 1
            while dst.exists():
                dst = notes_root / f"{stem}_{counter}{suffix}"
                counter += 1
        try:
            shutil.move(str(src), str(dst))
            moved_count += 1
        except Exception as e:
            sys.stderr.write(f"[delete_topic] move file failed: {src} -> {dst}: {e}\n")
            sys.stderr.flush()

    # 2. Remove empty topic directories (including subdirectories)
    if notes_topic_dir.exists():
        _remove_empty_dir(notes_topic_dir)
    if organized_topic_dir.exists():
        _remove_empty_dir(organized_topic_dir)

    # 3. Remove topic from WIKI.md
    wiki_ok, _ = _remove_topic_from_wiki(topic_name)
    if not wiki_ok:
        sys.stderr.write(f"[delete_topic] WIKI.md removal failed for {topic_name}\n")
        sys.stderr.flush()

    # 4. Clear YAML topic field from all moved files
    notes_root_files = set()
    for src in actual_files:
        dst = notes_root / src.name
        # Re-derive the actual destination path (accounting for conflict renames)
        stem = src.stem
        suffix = src.suffix
        candidate = notes_root / f"{stem}{suffix}"
        counter = 1
        while not candidate.exists():
            candidate = notes_root / f"{stem}_{counter}{suffix}"
            counter += 1
            if counter > 100:
                candidate = None
                break
        if candidate and candidate.exists():
            notes_root_files.add(candidate)
        else:
            notes_root_files.add(notes_root / src.name)

    for fp in notes_root_files:
        if fp.exists():
            try:
                _clear_topic_in_file(str(fp))
            except Exception as e:
                sys.stderr.write(f"[delete_topic] clear topic failed: {fp} - {e}\n")
                sys.stderr.flush()

    # 5. Re-assign topics for moved files
    reassigned_count = 0
    pending_count = 0

    for fp in notes_root_files:
        if not fp.exists():
            continue
        try:
            result = auto_assign_topic_for_file(str(fp))
            if result and result.get("status") == "auto_assigned":
                reassigned_count += 1
            else:
                pending_count += 1
        except Exception as e:
            sys.stderr.write(f"[delete_topic] reassign failed: {fp} - {e}\n")
            sys.stderr.flush()
            pending_count += 1

    return {
        "success": True,
        "message": f"已删除主题「{topic_name}」，{moved_count} 个文件移至 Notes 根目录，"
                   f"重新分配 {reassigned_count} 个，{pending_count} 个待确认",
        "reassigned": reassigned_count,
        "pending": pending_count,
        "moved": moved_count,
    }


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

        import shutil
        old_dir = workspace_path / config.NOTES_FOLDER / old_topic
        new_dir = workspace_path / config.NOTES_FOLDER / new_topic
        if old_dir.exists() and old_dir.is_dir():
            new_dir.mkdir(parents=True, exist_ok=True)
            for item in old_dir.iterdir():
                dst = new_dir / item.name
                if dst.exists():
                    if dst.is_dir():
                        shutil.rmtree(str(dst))
                    else:
                        dst.unlink()
                shutil.move(str(item), str(dst))
            shutil.rmtree(str(old_dir))

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


def create_topic(topic_name):
    """
    在 WIKI.md 中创建新的主题条目，支持多级路径（用 / 分隔）
    自动创建父级标题（如果不存在）
    """
    wiki_path = _get_wiki_path()
    workspace = config.workspace_path
    
    if not wiki_path or not workspace:
        return {"success": False, "message": "未设置工作区"}
    
    if not topic_name or not topic_name.strip():
        return {"success": False, "message": "主题名不能为空"}
    
    topic_name = topic_name.strip()
    if '/' in topic_name and TOPIC_SEP not in topic_name:
        topic_name = topic_name.replace('/', TOPIC_SEP)
    
    try:
        if wiki_path.exists():
            content = wiki_path.read_text(encoding='utf-8')
        else:
            wiki_path.parent.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
        
        headings = parse_wiki_headings()
        for h in headings:
            if h["name"].lower() == topic_name.lower():
                return {"success": False, "message": f"主题「{topic_name}」已存在"}
        
        parts = [p.strip() for p in topic_name.split(TOPIC_SEP) if p.strip()]
        if not parts:
            return {"success": False, "message": "主题名不能为空"}
        topic_leaf = parts[-1]
        topic_depth = len(parts)
        heading_prefix = '#' * (topic_depth + 1)

        new_topic_lines = [
            "",
            f"{heading_prefix} {topic_leaf}",
            "",
            "### 来源文件",
            "",
        ]
        
        lines = content.split('\n')
        
        if topic_depth > 1:
            parent_insert_idx = len(lines)
            for pi in range(len(parts) - 1):
                parent_label = parts[pi]
                parent_heading_prefix = '#' * (pi + 2)
                parent_heading = f'{parent_heading_prefix} {parent_label}'
                
                parent_found = False
                for i, line in enumerate(lines):
                    if line.strip() == parent_heading:
                        parent_found = True
                        parent_insert_idx = i + 1
                        while parent_insert_idx < len(lines):
                            next_stripped = lines[parent_insert_idx].strip()
                            next_heading_match = re.match(r'^(#{2,})\s+', next_stripped)
                            if next_heading_match:
                                next_level = len(next_heading_match.group(1))
                                if next_level <= pi + 2:
                                    break
                            parent_insert_idx += 1
                        break
                
                if not parent_found:
                    parent_section = [
                        '',
                        parent_heading,
                        ''
                    ]
                    for i, l in enumerate(parent_section):
                        lines.insert(parent_insert_idx + i, l)
                    parent_insert_idx += len(parent_section)
            
            for i, l in enumerate(new_topic_lines):
                lines.insert(parent_insert_idx + i, l)
        else:
            insert_idx = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                stripped = lines[i].strip()
                if re.match(r'^#{2,}\s+', stripped):
                    heading_match = re.match(r'^(#{2,})', stripped)
                    if heading_match:
                        existing_level = len(heading_match.group(1))
                        if existing_level <= 2:
                            if stripped[existing_level:].strip() != '目录':
                                insert_idx = i + 1
                                while insert_idx < len(lines):
                                    next_stripped = lines[insert_idx].strip()
                                    next_heading_match = re.match(r'^(#{2,})\s+', next_stripped)
                                    if next_heading_match:
                                        next_level = len(next_heading_match.group(1))
                                        if next_level <= 2:
                                            break
                                    insert_idx += 1
                                break
            
            new_lines = lines[:insert_idx] + new_topic_lines + lines[insert_idx:]
            lines = new_lines
        
        new_content = '\n'.join(lines)
        
        wiki_path.write_text(new_content, encoding='utf-8')

        notes_topic_dir = Path(workspace) / config.NOTES_FOLDER
        for part in parts:
            notes_topic_dir = notes_topic_dir / part
        notes_topic_dir.mkdir(parents=True, exist_ok=True)
        
        return {"success": True, "message": f"主题「{topic_name}」创建成功"}
        
    except Exception as e:
        sys.stderr.write(f"[create_topic] failed: {e}\n")
        sys.stderr.flush()
        return {"success": False, "message": f"创建失败: {e}"}


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
    wiki_path = workspace_path / "wiki" / "WIKI.md"

    file_topics = {}
    for md_file in md_files:
        if md_file.name == 'WIKI.md' and 'wiki' in md_file.parts:
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


