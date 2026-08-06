"""WIKI.md 核心解析模块 — 路径解析、标题解析、编号、综述开关解析

WIKI.md 的 CRUD 操作见 utils.wiki_crud，同步逻辑见 utils.wiki_sync，
去重逻辑见 utils.topic_dedup，sidecar 统一门面见 sidecar.wiki_utils。
"""

import re
from pathlib import Path
from typing import TypedDict

from config import config
from config.constants import TOPIC_SEP
from utils.logger import logger


class WikiTopic(TypedDict):
    name: str
    label: str
    files: list[str]


def _get_wiki_path(workspace_str=None):
    """Resolve WIKI.md path with legacy fallback.

    Prefers ``<ws>/wiki/WIKI.md`` (modern layout) but falls back to the legacy
    ``<ws>/WIKI.md`` (pre-wiki/ workspaces). Read/write of the index must agree,
    so all WIKI consumers go through this single provider.
    """
    if workspace_str is None:
        workspace_str = config.workspace_path
    if not workspace_str:
        return None
    ws = Path(workspace_str)
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
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return []
    try:
        text = wiki_path.read_text(encoding="utf-8")
    except Exception:
        return []
    headings: list[dict[str, int | str]] = []
    topic_stack: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "<!-- NOTEAI_TAGS_START -->":
            break
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


def parse_wiki_structure():
    workspace = config.workspace_path
    if not workspace:
        return []
    wiki_path = _get_wiki_path()
    if not wiki_path or not wiki_path.exists():
        return []
    try:
        text = wiki_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"[parse_wiki] read failed: {e}")
        return []

    topics: list[WikiTopic] = []
    lines = text.split("\n")
    current_topic: WikiTopic | None = None
    topic_stack: list[str] = []
    file_item_pattern = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*\s*$")

    def _flush():
        nonlocal current_topic
        if current_topic:
            topics.append(current_topic)
            current_topic = None

    for line in lines:
        stripped = line.strip()
        if stripped == "<!-- NOTEAI_TAGS_START -->":
            break

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


def collect_survey_off_topics(workspace_str=None) -> set[str]:
    wiki_path = _get_wiki_path(workspace_str)
    if not wiki_path or not wiki_path.exists():
        return set()
    try:
        lines = wiki_path.read_text(encoding="utf-8").split("\n")
    except Exception:
        return set()

    off_topics: set[str] = set()
    topic_stack: list[str] = []
    for idx, line in enumerate(lines):
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
        if idx + 1 < len(lines) and lines[idx + 1].strip() == "> 综述: off":
            off_topics.add(topic_path)
    return off_topics


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
