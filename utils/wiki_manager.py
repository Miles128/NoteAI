"""WIKI.md 管理模块 — 解析、读写、同步、去重、合并"""

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

from config.constants import TOPIC_SEP
from config.settings import config
from utils.logger import logger


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
    topic_stack = []
    for line in text.split('\n'):
        stripped = line.strip()
        match = re.match(r'^(#{2,4})\s+(.+)$', stripped)
        if not match:
            continue
        label = match.group(2).strip()
        if label in ('目录', '来源文件'):
            continue
        topic_level = len(match.group(1)) - 1
        while len(topic_stack) >= topic_level:
            topic_stack.pop()
        parent_path = topic_stack[-1] if topic_stack else ""
        topic_path = parent_path + TOPIC_SEP + label if parent_path else label
        topic_stack.append(topic_path)
        headings.append({"level": topic_level, "name": topic_path, "label": label})
    return headings


def _title_from_path(file_rel_path: str) -> str:
    """从文件相对路径提取标题（文件名 stem）"""
    return Path(file_rel_path).stem


def parse_wiki_structure():
    """解析 WIKI.md 的主题结构。

    新格式每行独立判断：
      ## / ### / #### … → 新主题段
      1. **标题**        → 当前主题下的文件（title 存入 files 列表）

    返回:
      [{"name": "full_topic_path", "label": "leaf_name", "files": ["title1", ...]}, ...]
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
    topic_stack = []
    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')

    def _flush():
        nonlocal current_topic
        if current_topic:
            topics.append(current_topic)
            current_topic = None

    for line in lines:
        stripped = line.strip()

        heading_match = re.match(r'^(#{2,})\s+(.+)$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            if heading_text in ('目录', '来源文件'):
                continue

            _flush()

            while len(topic_stack) >= level - 1:
                topic_stack.pop()

            parent_path = topic_stack[-1] if topic_stack else ''
            topic_path = (parent_path + TOPIC_SEP + heading_text) if parent_path else heading_text

            topic_stack.append(topic_path)
            current_topic = {"name": topic_path, "label": heading_text, "files": []}
            continue

        if current_topic:
            file_match = file_item_pattern.match(stripped)
            if file_match:
                current_topic['files'].append(file_match.group(2).strip())

    _flush()
    return topics


def add_file_to_wiki_topic(file_rel_path, topic, file_title=None):  # noqa: PLR0912, PLR0915
    """向 WIKI.md 添加文件到指定主题下。

    WIKI.md 格式（仅含标题 + 文件列表）::

        ## 一级主题
        1. **文件标题1**
        2. **文件标题2**

        ### 二级主题
        1. **文件标题3**
    """
    wiki_path = _get_wiki_path()
    workspace = config.workspace_path
    if not wiki_path or not workspace:
        return False

    if '/' in topic and TOPIC_SEP not in topic:
        topic = topic.replace('/', TOPIC_SEP)

    display_title = file_title or _title_from_path(file_rel_path)

    try:
        if wiki_path.exists():
            content = wiki_path.read_text(encoding='utf-8')
        else:
            wiki_path.parent.mkdir(parents=True, exist_ok=True)
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"
    except Exception as e:
        sys.stderr.write(f"[wiki] read failed: {e}\n")
        sys.stderr.flush()
        return False

    parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
    if not parts:
        return False
    topic_leaf = parts[-1]
    topic_depth = len(parts)
    heading_prefix = '#' * (topic_depth + 1)
    topic_heading = f'{heading_prefix} {topic_leaf}'

    lines = content.split('\n')
    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')

    # ---- ensure parent headings exist ----
    insert_base = len(lines)
    for pi in range(len(parts) - 1):
        parent_label = parts[pi]
        parent_prefix = '#' * (pi + 2)
        parent_heading = f'{parent_prefix} {parent_label}'
        found = False
        for idx, line in enumerate(lines):
            if line.strip() == parent_heading:
                found = True
                insert_base = idx + 1
                break
        if not found:
            new_section = ['', parent_heading, '']
            for j, sl in enumerate(new_section):
                lines.insert(insert_base + j, sl)
            insert_base += len(new_section)

    # ---- find topic heading ----
    topic_start = None
    topic_end = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == topic_heading:
            topic_start = i
        elif topic_start is not None and re.match(r'^#{2,}\s+', stripped):
            h_level = len(re.match(r'^(#{2,})', stripped).group(1))
            if h_level <= topic_depth + 1:
                topic_end = i
                break

    if topic_start is None:
        # create topic heading + file
        new_section = ['', topic_heading, '', f'1. **{display_title}**']
        for j, sl in enumerate(new_section):
            lines.insert(insert_base + j, sl)
    else:
        # add file under existing topic, after last file item
        last_file_idx = topic_start
        for i in range(topic_start + 1, topic_end):
            if file_item_pattern.match(lines[i].strip()):
                last_file_idx = i

        # check for duplicate
        for i in range(topic_start + 1, topic_end):
            fm = file_item_pattern.match(lines[i].strip())
            if fm and fm.group(2).strip() == display_title:
                return True  # already present

        lines.insert(last_file_idx + 1, f'0. **{display_title}**')

    # ---- re-number all topic sections ----
    _renumber_wiki_files(lines)

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


def rename_wiki_topic(old_topic, new_topic):  # noqa: PLR0912, PLR0915
    """重命名 WIKI.md 中的主题标题，返回该主题下的文件标题列表。"""
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
    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    new_lines = []
    in_target = False
    file_titles = []

    old_heading = f'## {old_topic}'
    new_heading = f'## {new_topic}'

    for line in lines:
        stripped = line.strip()
        if stripped == old_heading:
            in_target = True
            new_lines.append(new_heading)
            continue
        if in_target:
            if re.match(r'^#{2,}\s+', stripped):
                in_target = False
                new_lines.append(line)
                continue
            fm = file_item_pattern.match(stripped)
            if fm:
                file_titles.append(fm.group(2).strip())
            new_lines.append(line)
            continue
        new_lines.append(line)

    _renumber_wiki_files(new_lines)

    try:
        wiki_path.write_text('\n'.join(new_lines), encoding='utf-8')

        workspace = config.workspace_path
        if workspace:
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

        return True, file_titles
    except Exception as e:
        sys.stderr.write(f"[rename_topic] write failed: {e}\n")
        sys.stderr.flush()
        return False, []


def _renumber_wiki_files(lines):
    """重新编号 WIKI.md 中每个主题区域下的文件列表（1. 2. 3. ...）"""
    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    in_topic = False
    counter = 0
    result = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^#{2,}\s+', stripped) and stripped[2:].strip() not in ('目录', '来源文件'):
            in_topic = True
            counter = 0
            result.append(line)
        elif in_topic and re.match(r'^#{2,}\s+', stripped):
            result.append(line)
        elif in_topic:
            fm = file_item_pattern.match(stripped)
            if fm:
                counter += 1
                result.append(f'{counter}. **{fm.group(2)}**')
            else:
                result.append(line)
        else:
            result.append(line)
    lines[:] = result


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
                    if re.match(r'^\d+\.\s+\*\*', s):
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


def _merge_duplicate_topics_in_wiki():  # noqa: PLR0912, PLR0915
    """合并 WIKI.md 中同名（小写匹配）的重复主题段。"""
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return 0

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception:
        return 0

    lines = content.split('\n')
    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')

    # Collect sections by heading
    sections = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if re.match(r'^## (?!目录)', stripped):
            heading_name = stripped[3:].strip()
            section_lines = [lines[i]]
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if re.match(r'^## (?!目录)', s):
                    break
                section_lines.append(lines[j])
                j += 1
            sections.append({"name": heading_name, "start": i, "end": j, "lines": section_lines})
            i = j
        else:
            i += 1

    # Group by lowercase name
    groups = {}
    for sec in sections:
        key = sec["name"].lower()
        groups.setdefault(key, []).append(sec)

    merged = 0
    for group in groups.values():
        if len(group) <= 1:
            continue
        keeper = group[0]
        seen_titles = set()
        for line in keeper["lines"]:
            fm = file_item_pattern.match(line.strip())
            if fm:
                seen_titles.add(fm.group(2).strip())

        for dup in group[1:]:
            for line in dup["lines"]:
                fm = file_item_pattern.match(line.strip())
                if fm and fm.group(2).strip() not in seen_titles:
                    seen_titles.add(fm.group(2).strip())
                    keeper["lines"].append(f"{len(seen_titles)}. **{fm.group(2)}**")
            merged += 1

    if merged == 0:
        return 0

    # Rebuild lines
    remove_ranges = set()
    keeper_starts = {}
    for group in groups.values():
        if len(group) > 1:
            keeper = group[0]
            keeper_starts[keeper["start"]] = keeper["lines"]
            for dup in group:
                for idx in range(dup["start"], dup["end"]):
                    remove_ranges.add(idx if dup is not keeper else -1)
            # Don't remove keeper lines
            for idx in range(keeper["start"], keeper["end"]):
                remove_ranges.discard(idx)

    new_lines = []
    for i, line in enumerate(lines):
        if i in remove_ranges:
            continue
        if i in keeper_starts:
            for sl in keeper_starts[i]:
                new_lines.append(sl)
            continue
        new_lines.append(line)

    _renumber_wiki_files(new_lines)
    wiki_path.write_text('\n'.join(new_lines), encoding='utf-8')
    return merged


def _deduplicate_files_in_wiki():
    """按标题去重 WIKI.md 每个主题下的文件。"""
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return 0

    try:
        content = wiki_path.read_text(encoding='utf-8')
    except Exception:
        return 0

    lines = content.split('\n')
    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    new_lines = []
    i = 0
    removed = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        is_heading = bool(re.match(r'^#{2,}\s+', stripped)) and stripped[2:].strip() not in ('目录', '来源文件')

        if is_heading:
            new_lines.append(line)
            seen = set()
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if re.match(r'^#{2,}\s+', s):
                    break
                fm = file_item_pattern.match(s)
                if fm:
                    title = fm.group(2).strip()
                    if title not in seen:
                        seen.add(title)
                        new_lines.append(lines[j])
                    else:
                        removed += 1
                else:
                    new_lines.append(lines[j])
                j += 1
            i = j
        else:
            new_lines.append(line)
            i += 1

    if removed > 0:
        _renumber_wiki_files(new_lines)
        wiki_path.write_text('\n'.join(new_lines), encoding='utf-8')
    return removed


def _remove_topic_from_wiki(topic_name):
    """从 WIKI.md 移除整个主题段落（标题 + 文件列表），返回被移除的文件标题列表。"""
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
    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    new_lines = []
    in_target = False
    removed_titles = []
    target_heading = f'## {topic_name}'

    for line in lines:
        stripped = line.strip()
        if stripped == target_heading:
            in_target = True
            continue
        if in_target:
            if re.match(r'^#{2,}\s+', stripped):
                in_target = False
                new_lines.append(line)
                continue
            fm = file_item_pattern.match(stripped)
            if fm:
                removed_titles.append(fm.group(2).strip())
            continue
        new_lines.append(line)

    _renumber_wiki_files(new_lines)
    wiki_path.write_text('\n'.join(new_lines), encoding='utf-8')
    return True, removed_titles


def delete_topic(topic_name):  # noqa: PLR0912, PLR0915
    """
    删除主题：
    1. 将主题文件夹下所有文件移动到 Notes 根目录
    2. 从 WIKI.md 中移除整个主题
    3. 清除文件的 YAML topic 字段，等待重新分配
    4. 清理空的主题文件夹和综述文件

    返回: {"success": bool, "message": str, "reassigned": int, "pending": int}
    """
    from utils.topic_assigner import (  # noqa: PLC0415
        _clear_topic_in_file,
        _remove_empty_dir,
        auto_assign_topic_for_file,
    )

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
            max_conflict_attempts = 100
            if counter > max_conflict_attempts:
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


def rename_topic(old_topic, new_topic):  # noqa: PLR0911, PLR0912, PLR0915
    """
    重命名主题：
    1. 检查新主题名是否已存在
    2. 如果存在：合并文件（旧主题文件移到新主题，更新 YAML，删除旧主题）
    3. 如果不存在：按原来的方案（重命名 WIKI.md 标题 + 更新 YAML）

    返回: {"success": bool, "message": str, "updated": int, "merged": bool}
    """
    from utils.topic_assigner import write_topic_to_file  # noqa: PLC0415
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

        # files are now just title strings; derive paths from topic folder
        old_topic_parts = [p.strip() for p in old_topic.split(TOPIC_SEP) if p.strip()]
        old_topic_dir = workspace_path / config.NOTES_FOLDER
        for part in old_topic_parts:
            old_topic_dir = old_topic_dir / part

        old_file_titles = old_topic_data.get("files", [])
        for title in old_file_titles:
            fp = old_topic_dir / f"{title}.md"
            if fp.exists():
                write_topic_to_file(str(fp), new_topic)
                add_file_to_wiki_topic(str(fp), new_topic, title)

        _remove_topic_from_wiki(old_topic)
        _merge_duplicate_topics_in_wiki()
        _deduplicate_files_in_wiki()

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
            "message": f"已合并到「{new_topic}」，移动 {len(old_file_titles)} 个文件",
            "updated": len(old_file_titles),
            "merged": True
        }

    wiki_success, old_file_titles = rename_wiki_topic(old_topic, new_topic)

    old_topic_parts = [p.strip() for p in old_topic.split(TOPIC_SEP) if p.strip()]
    old_topic_dir = workspace_path / config.NOTES_FOLDER
    for part in old_topic_parts:
        old_topic_dir = old_topic_dir / part

    updated_count = 0
    for title in old_file_titles:
        full_path = old_topic_dir / f"{title}.md"
        if full_path.exists():
            try:
                write_topic_to_file(str(full_path), new_topic)
                updated_count += 1
            except Exception as e:
                sys.stderr.write(f"[rename_topic] update YAML failed: {title} - {e}\n")
                sys.stderr.flush()

    if not wiki_success and updated_count == 0:
        return {"success": False, "message": "重命名失败", "merged": False}

    return {
        "success": True,
        "message": f"已重命名主题，更新 {updated_count} 个文件",
        "updated": updated_count,
        "merged": False
    }


def remove_file_from_wiki_topic(file_rel_path):  # noqa: PLR0912
    """从 WIKI.md 中移除指定文件的记录。

    通过文件名 stem 匹配主题区域下的 ``N. **title**`` 行。
    返回: (success, old_topic_name)
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

    target_title = _title_from_path(file_rel_path)
    lines = content.split('\n')
    file_item_pattern = re.compile(r'^(\d+)\.\s+\*\*(.+?)\*\*\s*$')
    old_topic = None
    current_topic = None
    new_lines = []

    for line in lines:
        stripped = line.strip()
        heading_match = re.match(r'^(#{2,})\s+(.+)$', stripped)
        if heading_match:
            heading_text = heading_match.group(2).strip()
            if heading_text not in ('目录', '来源文件'):
                current_topic = heading_text
            new_lines.append(line)
            continue

        if current_topic:
            file_match = file_item_pattern.match(stripped)
            if file_match and file_match.group(2).strip() == target_title:
                old_topic = current_topic
                continue  # skip this file line

        new_lines.append(line)

    if old_topic:
        _renumber_wiki_files(new_lines)

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


def create_topic(topic_name):  # noqa: PLR0912
    """在 WIKI.md 中创建主题（仅添加标题，无文件列表）。"""
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
            content = f"# WIKI\n\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n主题数量: 0\n\n## 目录\n\n"

        for h in parse_wiki_headings():
            if h["name"].lower() == topic_name.lower():
                return {"success": False, "message": f"主题「{topic_name}」已存在"}

        parts = [p.strip() for p in topic_name.split(TOPIC_SEP) if p.strip()]
        if not parts:
            return {"success": False, "message": "主题名不能为空"}
        topic_leaf = parts[-1]
        heading_prefix = '#' * (len(parts) + 1)

        new_topic_lines = ['', f'{heading_prefix} {topic_leaf}', '']
        lines = content.split('\n')

        # ensure parent headings
        insert_idx = len(lines)
        for pi in range(len(parts) - 1):
            parent_label = parts[pi]
            parent_prefix = '#' * (pi + 2)
            parent_heading = f'{parent_prefix} {parent_label}'
            found = False
            for i, line in enumerate(lines):
                if line.strip() == parent_heading:
                    found = True
                    insert_idx = i + 1
                    break
            if not found:
                for j, sl in enumerate(['', parent_heading, '']):
                    lines.insert(insert_idx + j, sl)
                insert_idx += 3

        for j, sl in enumerate(new_topic_lines):
            lines.insert(insert_idx + j, sl)

        wiki_path.write_text('\n'.join(lines), encoding='utf-8')

        notes_topic_dir = Path(workspace) / config.NOTES_FOLDER
        for part in parts:
            notes_topic_dir = notes_topic_dir / part
        notes_topic_dir.mkdir(parents=True, exist_ok=True)

        return {"success": True, "message": f"主题「{topic_name}」创建成功"}

    except Exception as e:
        sys.stderr.write(f"[create_topic] failed: {e}\n")
        sys.stderr.flush()
        return {"success": False, "message": f"创建失败: {e}"}


def _collect_survey_off_topics(wiki_path: Path) -> set[str]:
    if not wiki_path.exists():
        return set()
    try:
        lines = wiki_path.read_text(encoding='utf-8').split('\n')
    except Exception:
        return set()

    off_topics = set()
    topic_stack = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r'^(#{2,4})\s+(.+)$', stripped)
        if not match:
            continue
        label = match.group(2).strip()
        if label in ('目录', '来源文件'):
            continue
        topic_level = len(match.group(1)) - 1
        while len(topic_stack) >= topic_level:
            topic_stack.pop()
        parent_path = topic_stack[-1] if topic_stack else ""
        topic_path = parent_path + TOPIC_SEP + label if parent_path else label
        topic_stack.append(topic_path)
        if idx + 1 < len(lines) and lines[idx + 1].strip() == '> 综述: off':
            off_topics.add(topic_path)
    return off_topics


def _write_file_topic_from_folder(file_path: Path, topic: str | None) -> bool:
    try:
        text = file_path.read_text(encoding='utf-8')
        had_bom = text.startswith('\ufeff')
        clean = text.lstrip('\ufeff')
        m = re.match(r'^(\s*---[ \t]*\r?\n)([\s\S]*?)(\r?\n---)', clean)
        if m:
            try:
                meta = yaml.safe_load(m.group(2)) or {}
            except Exception:
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            body = clean[m.end():].lstrip('\n')
        else:
            meta = {}
            body = clean

        before = meta.get('topic')
        if topic:
            meta['topic'] = topic
        else:
            meta.pop('topic', None)

        if before == meta.get('topic') and m:
            return False

        prefix = '\ufeff' if had_bom else ''
        if meta:
            fm = yaml.dump(meta, allow_unicode=True, default_flow_style=False).strip()
            new_text = prefix + '---\n' + fm + '\n---\n' + body
        else:
            new_text = prefix + body
        file_path.write_text(new_text, encoding='utf-8')
        return True
    except Exception as e:
        logger.warning(f"[wiki_sync] update file topic failed {file_path}: {e}")
        return False


def _is_hidden_path(path: Path) -> bool:
    return any(part.startswith('.') for part in path.parts)


def topic_from_notes_path(file_path: str | Path) -> str | None:
    """从 Notes/ 下的路径推导 topic（文件夹为准）；Notes 根目录或非 Notes 返回 None。"""
    workspace = config.workspace_path
    if not workspace:
        return None
    path = Path(file_path)
    notes_root = Path(workspace) / config.NOTES_FOLDER
    try:
        rel = path.relative_to(notes_root)
    except ValueError:
        return None
    if path.suffix.lower() != ".md":
        return None
    parts = rel.parts
    if len(parts) < 2:
        return None
    dir_parts = parts[:-1]
    if not dir_parts:
        return None
    if len(dir_parts) > 3:
        dir_parts = dir_parts[:3]
    return TOPIC_SEP.join(dir_parts)


def sync_wiki_with_files():  # noqa: PLR0912, PLR0915
    """Rebuild WIKI.md from the Notes folder hierarchy and align file frontmatter.

    Folder hierarchy under Notes is the source of truth. Empty topic folders are
    kept as WIKI headings; Markdown files directly under Notes are left unlisted
    and have their topic field cleared.
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "topics": 0, "files": 0, "updated": 0}

    workspace_path = Path(workspace)
    notes_root = workspace_path / config.NOTES_FOLDER
    wiki_path = _get_wiki_path()
    if not wiki_path:
        return {"success": False, "message": "WIKI.md 路径无效", "topics": 0, "files": 0, "updated": 0}

    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    off_topics = _collect_survey_off_topics(wiki_path)

    topic_files: dict[str, list[str]] = {}
    topic_parts: dict[str, tuple[str, ...]] = {}
    root_md_files: list[Path] = []
    updated_files = 0

    if notes_root.exists():
        for directory in sorted((p for p in notes_root.rglob('*') if p.is_dir()), key=lambda p: str(p.relative_to(notes_root))):
            try:
                rel_parts = directory.relative_to(notes_root).parts
            except ValueError:
                continue
            if not rel_parts or _is_hidden_path(Path(*rel_parts)):
                continue
            for depth in range(1, min(len(rel_parts), 3) + 1):
                parts = tuple(rel_parts[:depth])
                topic = TOPIC_SEP.join(parts)
                topic_parts.setdefault(topic, parts)
                topic_files.setdefault(topic, [])

        for md_file in sorted(notes_root.rglob('*.md'), key=lambda p: str(p.relative_to(notes_root))):
            try:
                rel_parts = md_file.relative_to(notes_root).parts
            except ValueError:
                continue
            if _is_hidden_path(Path(*rel_parts)) or md_file.name in ('WIKI.md', 'tags.md'):
                continue
            topic_dir_parts = rel_parts[:-1]
            if not topic_dir_parts:
                root_md_files.append(md_file)
                continue
            parts = tuple(topic_dir_parts[:3])
            topic = TOPIC_SEP.join(parts)
            topic_parts.setdefault(topic, parts)
            topic_files.setdefault(topic, []).append(md_file.stem)
            if _write_file_topic_from_folder(md_file, topic):
                updated_files += 1

    for md_file in root_md_files:
        if _write_file_topic_from_folder(md_file, None):
            updated_files += 1

    def _sort_key(item):
        topic, parts = item
        return parts

    lines = [
        "# WIKI",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"主题数量: {len(topic_parts)}",
        "",
        "## 目录",
        "",
    ]

    for topic, parts in sorted(topic_parts.items(), key=_sort_key):
        heading = "#" * (len(parts) + 1) + " " + parts[-1]
        lines.append(heading)
        if topic in off_topics:
            lines.append("> 综述: off")
        files = sorted(dict.fromkeys(topic_files.get(topic, [])))
        for idx, title in enumerate(files, 1):
            lines.append(f"{idx}. **{title}**")
        lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
    wiki_path.write_text(content, encoding='utf-8')

    return {
        "success": True,
        "message": f"同步完成：主题 {len(topic_parts)} 个，文件 {sum(len(v) for v in topic_files.values())} 个，更新 frontmatter {updated_files} 个",
        "topics": len(topic_parts),
        "files": sum(len(v) for v in topic_files.values()),
        "updated": updated_files,
    }


