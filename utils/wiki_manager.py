"""WIKI.md 核心解析模块 — 路径解析、标题解析、编号

WIKI.md 的 CRUD 操作见 utils.topic_wiki_manager
去重逻辑见 utils.topic_dedup
"""

import re
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
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
        text = wiki_path.read_text(encoding="utf-8")
    except Exception:
        return []
    headings = []
    topic_stack = []
    for line in text.split("\n"):
        stripped = line.strip()
        match = re.match(r"^(#{2,4})\s+(.+)$", stripped)
        if not match:
            continue
        label = match.group(2).strip()
        if label in ("目录", "来源文件"):
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
    return Path(file_rel_path).stem


def parse_wiki_structure():
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = Path(workspace) / "wiki" / "WIKI.md"
    if not wiki_path.exists():
        return []
    try:
        text = wiki_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"[parse_wiki] read failed: {e}")
        return []

    topics = []
    lines = text.split("\n")
    current_topic = None
    topic_stack = []
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")

    def _flush():
        nonlocal current_topic
        if current_topic:
            topics.append(current_topic)
            current_topic = None

    for line in lines:
        stripped = line.strip()

        heading_match = re.match(r"^(#{2,})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()

            if heading_text in ("目录", "来源文件"):
                continue

            _flush()

            while len(topic_stack) >= level - 1:
                topic_stack.pop()

            parent_path = topic_stack[-1] if topic_stack else ""
            topic_path = (parent_path + TOPIC_SEP + heading_text) if parent_path else heading_text

            topic_stack.append(topic_path)
            current_topic = {"name": topic_path, "label": heading_text, "files": []}
            continue

        if current_topic:
            file_match = file_item_pattern.match(stripped)
            if file_match:
                current_topic["files"].append(file_match.group(2).strip())

    _flush()
    return topics


def _renumber_wiki_files(lines):
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")
    in_topic = False
    counter = 0
    result = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#{2,}\s+", stripped) and stripped[2:].strip() not in ("目录", "来源文件"):
            in_topic = True
            counter = 0
            result.append(line)
        elif in_topic and re.match(r"^#{2,}\s+", stripped):
            result.append(line)
        elif in_topic:
            fm = file_item_pattern.match(stripped)
            if fm:
                counter += 1
                result.append(f"{counter}. **{fm.group(2)}**")
            else:
                result.append(line)
        else:
            result.append(line)
    lines[:] = result


# --- Re-exported functions from topic_dedup and topic_wiki_manager ---
# Imports are deferred to function bodies to avoid circular imports
# (topic_dedup / wiki_crud / wiki_sync all import from this module).


def _remove_empty_topic_sections(topic_name_lower):
    from utils.topic_dedup import _remove_empty_topic_sections as _impl

    return _impl(topic_name_lower)


def _merge_duplicate_topics_in_wiki():
    from utils.topic_dedup import _merge_duplicate_topics_in_wiki as _impl

    return _impl()


def _deduplicate_files_in_wiki():
    from utils.topic_dedup import _deduplicate_files_in_wiki as _impl

    return _impl()


def add_file_to_wiki_topic(file_rel_path, topic, file_title=None):
    from utils.topic_wiki_manager import add_file_to_wiki_topic as _impl

    return _impl(file_rel_path, topic, file_title=file_title)


def remove_file_from_wiki_topic(file_rel_path):
    from utils.topic_wiki_manager import remove_file_from_wiki_topic as _impl

    return _impl(file_rel_path)


def rename_wiki_topic(old_topic, new_topic):
    from utils.topic_wiki_manager import rename_wiki_topic as _impl

    return _impl(old_topic, new_topic)


def _remove_topic_from_wiki(topic_name):
    from utils.topic_wiki_manager import _remove_topic_from_wiki as _impl

    return _impl(topic_name)


def create_topic(topic_name):
    from utils.topic_wiki_manager import create_topic as _impl

    return _impl(topic_name)


def rename_topic(old_topic, new_topic):
    from utils.topic_wiki_manager import rename_topic as _impl

    return _impl(old_topic, new_topic)


def delete_topic(topic_name):
    from utils.topic_wiki_manager import delete_topic as _impl

    return _impl(topic_name)


def sync_wiki_with_files():
    from utils.topic_wiki_manager import sync_wiki_with_files as _impl

    return _impl()


def _write_file_topic_from_folder(file_path, topic):
    from utils.topic_wiki_manager import _write_file_topic_from_folder as _impl

    return _impl(file_path, topic)


def topic_from_notes_path(file_path):
    from utils.topic_wiki_manager import topic_from_notes_path as _impl

    return _impl(file_path)
