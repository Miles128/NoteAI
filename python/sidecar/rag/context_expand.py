"""Lightweight retrieval expansion: confirmed backlinks + topic surveys (not full Graph RAG)."""

from __future__ import annotations

from pathlib import Path

from config import config
from config.constants import TOPIC_SEP
from sidecar.cascade import get_survey_path
from sidecar.textutils import parse_frontmatter
from utils.link_indexer import load_links
from utils.logger import logger

_MAX_SURVEY_TOPICS = 2
_MAX_SURVEY_CHARS = 2800
_MAX_BACKLINK_FILES = 4
_MAX_BACKLINK_CHARS = 700
_BACKLINK_SCORE = 0.25


def _confirmed_neighbor_paths(file_path: str) -> list[str]:
    neighbors: list[str] = []
    seen: set[str] = set()
    for link in load_links().get("links", []):
        if link.get("status") != "confirmed":
            continue
        other = ""
        if link.get("from") == file_path:
            other = link.get("to", "")
        elif link.get("to") == file_path:
            other = link.get("from", "")
        if other and other not in seen:
            seen.add(other)
            neighbors.append(other)
    return neighbors


def _read_file_excerpt(workspace: str, rel_path: str, max_chars: int) -> str:
    path = Path(workspace) / rel_path
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    _meta, body = parse_frontmatter(text)
    body = (body or text).strip()
    if len(body) <= max_chars:
        return body
    return body[:max_chars] + "…"


def _fetch_indexed_chunks(workspace: str, rel_path: str, limit: int = 2) -> list[dict]:
    from sidecar.rag.index import fetch_chunks_by_file

    return fetch_chunks_by_file(workspace, rel_path, limit=limit)


def _survey_items(workspace: str, topic_keys: list[str]) -> list[dict]:
    items: list[dict] = []
    seen_topics: set[str] = set()

    for raw in topic_keys:
        topic = (raw or "").strip()
        if not topic or topic in seen_topics:
            continue
        seen_topics.add(topic)
        if len(items) >= _MAX_SURVEY_TOPICS:
            break

        survey_path = get_survey_path(topic)
        if not survey_path or not survey_path.is_file():
            continue
        try:
            rel = str(survey_path.relative_to(workspace))
            text = survey_path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            continue

        _meta, body = parse_frontmatter(text)
        body = (body or text).strip()
        if not body:
            continue
        if len(body) > _MAX_SURVEY_CHARS:
            body = body[:_MAX_SURVEY_CHARS] + "…"

        leaf = topic.rsplit(TOPIC_SEP, maxsplit=1)[-1]
        items.append(
            {
                "id": f"survey::{topic}",
                "content": body,
                "file_path": rel,
                "file_name": survey_path.name,
                "topic": topic,
                "source_type": "survey",
                "source_label": f"主题综述·{leaf}",
                "score": 0.95,
            }
        )
    return items


def _backlink_items(workspace: str, seed_paths: list[str], exclude: set[str]) -> list[dict]:
    items: list[dict] = []
    added: set[str] = set()

    for seed in seed_paths:
        if len(items) >= _MAX_BACKLINK_FILES:
            break
        for neighbor in _confirmed_neighbor_paths(seed):
            if neighbor in exclude or neighbor in added:
                continue
            if len(items) >= _MAX_BACKLINK_FILES:
                break

            try:
                chunks = _fetch_indexed_chunks(workspace, neighbor, limit=1)
            except Exception:
                chunks = []
            if chunks:
                chunk = chunks[0]
                content = (chunk.get("content") or "")[:_MAX_BACKLINK_CHARS]
            else:
                content = _read_file_excerpt(workspace, neighbor, _MAX_BACKLINK_CHARS)

            if not content.strip():
                continue

            added.add(neighbor)
            name = Path(neighbor).name
            items.append(
                {
                    "id": f"backlink::{neighbor}",
                    "content": content,
                    "file_path": neighbor,
                    "file_name": name,
                    "topic": chunks[0].get("topic", "") if chunks else "",
                    "source_type": "backlink",
                    "source_label": f"关联笔记·{name}",
                    "score": _BACKLINK_SCORE,
                    "linked_from": seed,
                }
            )
    return items


def expand_retrieval_context(
    results: list[dict],
    topics: list | None = None,
    workspace: str | None = None,
) -> list[dict]:
    """
    Prepend topic surveys and append 1-hop confirmed backlink excerpts.
    Vector hits keep source_type 'vector' (default).
    """
    ws = workspace or config.workspace_path
    if not ws or not results:
        survey_only = _survey_items(ws, list(topics or []))
        return survey_only if survey_only else results

    topic_keys: list[str] = []
    if topics:
        topic_keys.extend(t for t in topics if t)
    seed_paths: list[str] = []
    exclude: set[str] = set()

    expanded: list[dict] = []
    for r in results:
        row = dict(r)
        row.setdefault("source_type", "vector")
        fp = row.get("file_path", "")
        if fp:
            seed_paths.append(fp)
            exclude.add(fp)
            name = row.get("file_name") or Path(fp).name
            row.setdefault("source_label", name)
        t = row.get("topic", "")
        if t:
            topic_keys.append(t)
        expanded.append(row)

    surveys = _survey_items(ws, topic_keys)
    backlinks = _backlink_items(ws, seed_paths, exclude)

    out: list[dict] = []
    seen_ids: set[str] = set()
    for item in surveys + expanded + backlinks:
        iid = item.get("id", "")
        if iid and iid in seen_ids:
            continue
        if iid:
            seen_ids.add(iid)
        out.append(item)

    if surveys or backlinks:
        logger.info(f"[rag/context_expand] surveys={len(surveys)} backlinks={len(backlinks)} vector={len(expanded)}")
    return out
