"""主题可信度元数据组装（只读）。

从 sidecar/handlers/topics_handler.py::_topic_meta 下沉。
"""

from __future__ import annotations

from sidecar.topics.wiki_meta import latest_note_mtime, parse_topic_wiki_meta, read_topic_state
from utils.logger import logger
from utils.topic.stale import _parse_iso_timestamp


def build_topic_meta(topic: str, workspace: str) -> dict:
    """主题可信度元数据（只读）：来源数/冲突待处理数/编译时间/是否过期。"""
    try:
        wiki_meta = parse_topic_wiki_meta(topic)
    except Exception as e:
        logger.warning(f"[topics/meta] parse wiki meta failed: {e}\n")
        wiki_meta = None
    state = read_topic_state(workspace, topic)
    if wiki_meta is None and state is None:
        try:
            latest = latest_note_mtime(topic, workspace)
        except Exception:
            latest = None
        if latest is None:
            return {"exists": False}
    wiki_meta = wiki_meta or {}
    stats = state.get("stats") if state else None
    stats_documents = stats.get("documents") if isinstance(stats, dict) else None
    try:
        source_count = int(stats_documents if isinstance(stats_documents, int) else wiki_meta.get("source_count", 0))
    except (TypeError, ValueError):
        source_count = 0
    compiled_at = state.get("generated_at") if state else None
    is_stale = False
    try:
        latest_mtime = latest_note_mtime(topic, workspace)
    except Exception:
        latest_mtime = None
    if latest_mtime is not None:
        compiled_ts = _parse_iso_timestamp(compiled_at)
        is_stale = compiled_ts is None or latest_mtime > compiled_ts
    return {
        "exists": True,
        "source_count": source_count,
        "compiled_at": compiled_at,
        "is_stale": is_stale,
    }
