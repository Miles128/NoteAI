"""Detect topic surveys whose source notes are newer than compiled state."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from config import config
from config.constants import WORKSPACE_APP_FOLDER
from utils.text_utils import parse_frontmatter
from utils.topic.membership import note_belongs_to_topic, split_topic_parts


def _parse_iso_timestamp(value) -> float | None:
    """将 ISO 时间字符串转为 epoch 秒，失败返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def collect_stale_topics(workspace: str) -> list[str]:
    """轻量 stale 扫描：仅检查已有 topic_states 的主题，判定逻辑与 get_survey_overview 一致。

    单次全库遍历：一次 rglob + 逐文件头部 frontmatter 解析，按候选主题聚合
    最新 mtime，避免逐主题调用 collect_topic_notes 造成 O(主题数×全库文件数)。
    """
    states_dir = Path(workspace) / WORKSPACE_APP_FOLDER / "compiler" / "topic_states"
    if not states_dir.is_dir():
        return []
    candidates: list[tuple[str, float]] = []
    for state_file in sorted(states_dir.glob("*.json")):
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        topic = data.get("topic")
        compiled_ts = _parse_iso_timestamp(data.get("generated_at"))
        if not topic or compiled_ts is None:
            continue
        candidates.append((str(topic), compiled_ts))
    if not candidates:
        return []

    ws = Path(workspace)
    notes_dir = ws / config.NOTES_FOLDER
    notes_dir_exists = notes_dir.exists()
    topic_parts_cache: dict[str, list[str]] = {}
    latest_mtime: dict[str, float] = {}
    for md_file in ws.rglob("*.md"):
        if md_file.name.startswith("."):
            continue
        if "wiki" in md_file.parts:
            continue
        if md_file.name.endswith("_综述.md") or md_file.name.endswith("综述.md"):
            continue
        try:
            # 只读文件头部解析 frontmatter（同 collect_topic_notes 轻量模式），大文件不读全文
            with md_file.open("r", encoding="utf-8") as fh:
                text = fh.read(8192)
            fm, _body = parse_frontmatter(text)
        except Exception:
            continue
        file_topic = ""
        file_topics: list = []
        if fm:
            ft = fm.get("topic", "")
            if isinstance(ft, str):
                file_topic = ft
            fts = fm.get("topics", [])
            if isinstance(fts, list):
                file_topics = fts
        rel_parts: tuple = ()
        if notes_dir_exists:
            try:
                rel_parts = md_file.relative_to(notes_dir).parts
            except ValueError:
                rel_parts = ()
        try:
            mtime = md_file.stat().st_mtime
        except OSError:
            continue
        for topic, _compiled_ts in candidates:
            parts = topic_parts_cache.get(topic)
            if parts is None:
                parts = split_topic_parts(topic)
                topic_parts_cache[topic] = parts
            if note_belongs_to_topic(topic, file_topic, file_topics, rel_parts, parts):
                if mtime > latest_mtime.get(topic, float("-inf")):
                    latest_mtime[topic] = mtime

    stale: list[str] = []
    for topic, compiled_ts in candidates:
        latest = latest_mtime.get(topic)
        if latest is not None and latest > compiled_ts:
            stale.append(topic)
    return stale
