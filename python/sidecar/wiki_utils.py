"""WIKI.md unified interface — single source of truth for all WIKI.md I/O.

All WIKI.md read/write operations MUST go through this module.
Downstream code should never open/read/write WIKI.md directly.

Lower-level helpers live in:
  - utils.wiki_manager: path resolution, heading parsing, renumbering
  - utils.topic_wiki_manager: CRUD (add/remove/rename topics & files, sync)
  - utils.topic_dedup: merge/dedup
"""

import re
from datetime import datetime
from pathlib import Path

from config import config
from config.constants import TOPIC_SEP

from utils.wiki_manager import (
    _get_wiki_path,
    _renumber_wiki_files,
    parse_wiki_headings as _parse_wiki_headings_full,
    parse_wiki_structure as _parse_wiki_structure_full,
)


def resolve_wiki_path(workspace_str: str | Path | None = None) -> Path:
    if workspace_str is None:
        workspace_str = config.workspace_path or ""
    ws = Path(workspace_str)
    new_path = ws / "wiki" / "WIKI.md"
    if new_path.exists():
        return new_path
    old_path = ws / "WIKI.md"
    if old_path.exists():
        return old_path
    return new_path


def parse_wiki_headings() -> list:
    return _parse_wiki_headings_full()


def parse_wiki_structure() -> list:
    return _parse_wiki_structure_full()


def add_file_to_wiki_topic(file_rel_path, topic, file_title=None):
    from utils.topic_wiki_manager import add_file_to_wiki_topic as _impl

    return _impl(file_rel_path, topic, file_title)


def remove_file_from_wiki_topic(file_rel_path):
    from utils.topic_wiki_manager import remove_file_from_wiki_topic as _impl

    return _impl(file_rel_path)


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


def write_file_topic_from_folder(file_path: Path, topic: str | None) -> bool:
    from utils.topic_wiki_manager import _write_file_topic_from_folder as _impl

    return _impl(file_path, topic)


def topic_from_notes_path(file_path: str | Path) -> str | None:
    from utils.topic_wiki_manager import topic_from_notes_path as _impl

    return _impl(file_path)


def read_wiki_text(workspace_str: str | Path | None = None) -> str | None:
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
        return None
    try:
        return wiki_path.read_text(encoding="utf-8")
    except Exception:
        return None


def write_wiki_text(content: str, workspace_str: str | Path | None = None) -> bool:
    wiki_path = resolve_wiki_path(workspace_str)
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        wiki_path.write_text(content, encoding="utf-8")
        return True
    except Exception:
        return False


def ensure_wiki_exists(workspace_str: str | Path | None = None) -> Path:
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
        wiki_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            f"# WIKI\n\n"
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"主题数量: 0\n\n"
            f"## 目录\n\n"
        )
        wiki_path.write_text(content, encoding="utf-8")
    return wiki_path


def get_all_topic_names(workspace_str: str | Path | None = None) -> list[str]:
    headings = _parse_wiki_headings_full()
    return [h["name"] for h in headings]


def get_survey_status(workspace_str: str | Path | None = None) -> dict[str, bool]:
    text = read_wiki_text(workspace_str)
    if text is None:
        return {}
    lines = text.split("\n")
    surveys: dict[str, bool] = {}
    current_parent = ""
    for i in range(len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("## "):
            current_parent = stripped[3:].strip()
            is_off = (
                i + 1 < len(lines)
                and lines[i + 1].strip() == "> 综述: off"
            )
            surveys[current_parent] = not is_off
        elif stripped.startswith("### ") and current_parent:
            child = stripped[4:].strip()
            full = f"{current_parent}{TOPIC_SEP}{child}"
            parent_on = surveys.get(current_parent, True)
            if parent_on:
                surveys[full] = False
            else:
                is_off = (
                    i + 1 < len(lines)
                    and lines[i + 1].strip() == "> 综述: off"
                )
                surveys[full] = not is_off
    return surveys


def toggle_survey(
    topic_name: str,
    workspace_str: str | Path | None = None,
) -> dict:
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
        return {"success": False, "message": "WIKI.md 不存在"}

    try:
        text = wiki_path.read_text(encoding="utf-8")
    except Exception:
        return {"success": False, "message": "读取 WIKI.md 失败"}

    lines = text.split("\n")
    new_lines: list[str] = []
    current_parent = ""
    is_parent = TOPIC_SEP not in topic_name
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        new_lines.append(lines[i])

        if stripped.startswith("## "):
            current_parent = stripped[3:].strip()

            if is_parent and current_parent == topic_name:
                if i + 1 < len(lines) and lines[i + 1].strip() == "> 综述: off":
                    i += 1
                else:
                    new_lines.append("> 综述: off")
                    i += 1
                i += 1
                while i < len(lines):
                    s = lines[i].strip()
                    if s.startswith("## "):
                        new_lines.append(lines[i])
                        i += 1
                        break
                    if s.startswith("### ") and current_parent:
                        child = s[4:].strip()
                        full = f"{current_parent}{TOPIC_SEP}{child}"
                        new_lines.append(lines[i])
                        i += 1
                        if i < len(lines) and lines[i].strip() == "> 综述: off":
                            i += 1
                        while i < len(lines):
                            ns = lines[i].strip()
                            if ns.startswith("## ") or ns.startswith("### "):
                                break
                            new_lines.append(lines[i])
                            i += 1
                    else:
                        new_lines.append(lines[i])
                        i += 1
                        if s.startswith("## "):
                            break
                continue
        elif stripped.startswith("### ") and current_parent and not is_parent:
            child = stripped[4:].strip()
            full = f"{current_parent}{TOPIC_SEP}{child}"
            if full == topic_name:
                if i + 1 < len(lines) and lines[i + 1].strip() == "> 综述: off":
                    i += 1
                else:
                    new_lines.append("> 综述: off")
                    i += 1
                i += 1
                continue

        i += 1

    wiki_path.write_text("\n".join(new_lines), encoding="utf-8")
    return {"success": True, "message": "已切换综述状态"}


def collect_survey_off_topics(
    workspace_str: str | Path | None = None,
) -> set[str]:
    wiki_path = resolve_wiki_path(workspace_str)
    if not wiki_path.exists():
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
