"""WIKI.md 主题段头元数据解析与主题可信度状态读取。

从 sidecar/handlers/topics_handler.py 下沉；topics_handler 保留 re-export
以兼容既有测试的 import 路径。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from config.constants import TOPIC_SEP, WORKSPACE_APP_FOLDER
from sidecar.wiki_utils import read_wiki_text

_HEADING_RE = re.compile(r"^(#{2,4})\s+(.+)$")
_META_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


def parse_heading_comment(comment: str) -> dict:
    """解析段头注释内容，兼容 JSON 对象与 `key: value` 行两种格式。"""
    body = comment.strip()
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            return data
    except (TypeError, ValueError):
        pass
    result: dict = {}
    for line in body.splitlines():
        key, sep, value = line.strip().partition(":")
        if sep and key.strip():
            result[key.strip()] = value.strip()
    return result


def parse_topic_wiki_meta(topic: str) -> dict | None:
    """读取 WIKI.md 中指定主题段头的 HTML 注释元数据。

    Returns:
        dict —— 主题段存在（元数据可能为空字典）；None —— WIKI.md 不存在或主题段不存在。
    """
    text = read_wiki_text()
    if text is None:
        return None
    topic_stack: list[str] = []
    found = False
    section_lines: list[str] = []
    comment_balance = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped == "<!-- NOTEAI_TAGS_START -->":
            break
        match = _HEADING_RE.match(stripped)
        if match:
            if found:
                break
            label = match.group(2).strip()
            if label in ("目录", "来源文件"):
                continue
            level = len(match.group(1)) - 1
            while len(topic_stack) >= level:
                topic_stack.pop()
            parent = topic_stack[-1] if topic_stack else ""
            full = f"{parent}{TOPIC_SEP}{label}" if parent else label
            topic_stack.append(full)
            if full == topic:
                found = True
                section_lines = []
                comment_balance = 0
            continue
        if found:
            section_lines.append(line)
            comment_balance += stripped.count("<!--") - stripped.count("-->")
            if comment_balance <= 0 and stripped and not stripped.startswith("<!--") and "-->" not in stripped:
                break
    if not found:
        return None
    meta: dict = {}
    for m in _META_COMMENT_RE.finditer("\n".join(section_lines)):
        meta.update(parse_heading_comment(m.group(1)))
    return meta


def read_topic_state(workspace: str, topic: str) -> dict | None:
    """读取主题的语义编译状态文件（topic_states/{topic_id}.json），不存在时返回 None。"""
    from sidecar.semantic.ids import stable_id

    topic_id = stable_id("top", topic.casefold())
    state_path = Path(workspace) / WORKSPACE_APP_FOLDER / "compiler" / "topic_states" / f"{topic_id}.json"
    if not state_path.is_file():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def latest_note_mtime(topic: str, workspace: str) -> float | None:
    """主题下源笔记的最新 mtime（复用 get_survey_overview 同款 collect_topic_notes 判定）。"""
    from sidecar.cascade import collect_topic_notes

    ws = Path(workspace)
    mtimes: list[float] = []
    for note in collect_topic_notes(topic, include_content=False):
        note_path = ws / note["file_path"]
        try:
            mtimes.append(note_path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes) if mtimes else None
