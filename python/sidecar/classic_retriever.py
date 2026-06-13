"""Classic retrieval: topic tree + full-text search (no vector RAG)."""

from __future__ import annotations

from pathlib import Path

from config import config
from sidecar.rag.context_expand import (
    _MAX_BACKLINK_CHARS,
    _MAX_BACKLINK_FILES,
    _MAX_SURVEY_CHARS,
    _BACKLINK_SCORE,
    _backlink_items,
    _confirmed_neighbor_paths,
    _read_file_excerpt,
    _survey_items,
)
from sidecar.textutils import parse_frontmatter
from utils.fulltext_index import fulltext_index

DEFAULT_TOP_K = 8
_MAX_CHARS_PER_FILE = 4000
_MAX_TOPIC_LABELS = 40


def _file_title(text: str, rel_path: str) -> str:
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return Path(rel_path).stem


def _matches_topic_filter(file_topic: str, topics: list[str] | None) -> bool:
    if not topics:
        return True
    file_topic = (file_topic or "").strip()
    if not file_topic:
        return False
    return any(t and t in file_topic for t in topics)


def _matches_tag_filter(file_tags: list[str], tags: list[str] | None) -> bool:
    if not tags:
        return True
    return any(t in file_tags for t in tags if t)


def _parse_tags(raw_tags) -> list[str]:
    if isinstance(raw_tags, list):
        return [str(t).strip() for t in raw_tags if t]
    if isinstance(raw_tags, str) and raw_tags.strip():
        return [raw_tags.strip()]
    return []


def _topic_tree_context(workspace: str) -> dict | None:
    from utils.topic_manager import TopicManager

    labels = TopicManager.collect_topic_labels(workspace)
    if not labels:
        return None
    preview = "、".join(labels[:_MAX_TOPIC_LABELS])
    if len(labels) > _MAX_TOPIC_LABELS:
        preview += f" 等共 {len(labels)} 个主题"
    return {
        "id": "topic_tree",
        "content": f"工作区主题结构：{preview}",
        "file_path": "",
        "file_name": "",
        "topic": "",
        "source_type": "topic_tree",
        "source_label": "主题树",
        "score": 1.0,
    }


def retrieve(
    query: str,
    topics: list | None = None,
    tags: list | None = None,
    progress_callback=None,
) -> list[dict]:
    workspace = config.workspace_path
    if not workspace or not (query or "").strip():
        return []

    ws = Path(workspace)
    if not ws.is_dir():
        return []

    topic_filter = [str(t).strip() for t in (topics or []) if str(t).strip()]
    tag_filter = [str(t).strip() for t in (tags or []) if str(t).strip()]

    results: list[dict] = []
    tree_ctx = _topic_tree_context(workspace)
    if tree_ctx:
        results.append(tree_ctx)

    raw_hits = fulltext_index.search(query.strip(), max_results=30)
    seen_paths: set[str] = set()
    file_hits: list[dict] = []

    for item in raw_hits:
        rel = item.get("path", "")
        if not rel or rel in seen_paths:
            continue
        fpath = ws / rel
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
        except OSError:
            continue

        fm, body = parse_frontmatter(text)
        fm = fm or {}
        file_topic = str(fm.get("topic") or "").strip()
        if isinstance(fm.get("topic"), list):
            parts = [str(t).strip() for t in fm.get("topic") if t]
            file_topic = parts[0] if parts else ""

        file_tags = _parse_tags(fm.get("tags", []))
        if not _matches_topic_filter(file_topic, topic_filter):
            continue
        if not _matches_tag_filter(file_tags, tag_filter):
            continue

        body = (body or text).strip()
        if len(body) > _MAX_CHARS_PER_FILE:
            body = body[:_MAX_CHARS_PER_FILE] + "…"

        seen_paths.add(rel)
        title = _file_title(text, rel)
        file_hits.append({
            "id": f"fulltext::{rel}",
            "content": body,
            "file_path": rel,
            "file_name": Path(rel).name,
            "topic": file_topic,
            "source_type": "fulltext",
            "source_label": title,
            "score": float(item.get("score", 0)),
        })
        if len(file_hits) >= DEFAULT_TOP_K:
            break

    topic_keys = list(topic_filter)
    for hit in file_hits:
        t = hit.get("topic", "")
        if t:
            topic_keys.append(t)

    surveys = _survey_items(workspace, topic_keys)
    backlinks = _backlink_items(workspace, [h["file_path"] for h in file_hits], set(seen_paths))

    out: list[dict] = []
    seen_ids: set[str] = set()
    for item in results + surveys + file_hits + backlinks:
        iid = item.get("id", "")
        if iid and iid in seen_ids:
            continue
        if iid:
            seen_ids.add(iid)
        out.append(item)

    if progress_callback:
        progress_callback(len(out), len(out), "classic retrieval done")

    return out
