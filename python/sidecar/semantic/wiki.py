"""Object-summary semantic Wiki pages for topic states.

All topic pages are aggregated into one file per top-level topic (e.g.
`AI应用图鉴_语义.md`), with descendant topics rendered as nested sections,
mirroring the WIKI.md bookshelf layout.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config.constants import ABSTRACT_FOLDER, TOPIC_SEP
from sidecar.semantic.ids import content_hash, stable_id
from sidecar.semantic.store import SemanticStore
from sidecar.semantic.topic_state import build_topic_state

_UNSAFE_PATH = re.compile(r'[\\/:*?"<>|]')

# 主题页对象摘要：与语义工作台降级策略一致，低频低置信度对象不展示。
_SUMMARY_MIN_MENTIONS = 2
_SUMMARY_MIN_CONFIDENCE = 0.6
_SUMMARY_LIMIT = 6
_SUMMARY_DESC_CHARS = 60


def _safe_segment(value: str) -> str:
    cleaned = _UNSAFE_PATH.sub("_", value.strip()).strip(". ")
    return cleaned or "未命名主题"


def top_level_topic(topic: str) -> str:
    """Return the top-level segment of a topic path (e.g. `A > B` -> `A`)."""
    parts = [part for part in topic.split(TOPIC_SEP) if part.strip()]
    return parts[0] if parts else topic


def _target_path(store: SemanticStore, topic: str) -> Path:
    top = _safe_segment(top_level_topic(topic))
    return store.workspace / ABSTRACT_FOLDER / "semantic" / f"{top}_语义.md"


def _topic_object_summary(store: SemanticStore, topic: str) -> list[dict]:
    """Return top entities/concepts mentioned in a topic's documents.

    Deterministic and free of LLM calls: the summary is a quality-gated,
    frequency-ranked list of extracted objects.
    """
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT m.object_kind AS kind, m.object_id AS id,
                      CASE m.object_kind WHEN 'entity' THEN e.canonical_name ELSE c.canonical_name END AS name,
                      CASE m.object_kind WHEN 'entity' THEN e.description ELSE c.description END AS description,
                      COALESCE(CASE m.object_kind WHEN 'entity' THEN e.confidence ELSE c.confidence END, 0.0)
                          AS confidence,
                      COUNT(*) AS mention_count
               FROM semantic_mentions m
               JOIN blocks b ON b.id = m.block_id
               JOIN documents d ON d.id = b.document_id
               LEFT JOIN entities e
                 ON m.object_kind = 'entity' AND e.id = m.object_id AND e.status = 'active'
               LEFT JOIN concepts c
                 ON m.object_kind = 'concept' AND c.id = m.object_id AND c.status = 'active'
               WHERE d.topic = ? AND m.object_kind IN ('entity', 'concept')
               GROUP BY m.object_kind, m.object_id
               ORDER BY mention_count DESC, name
               LIMIT ?""",
            (topic, _SUMMARY_LIMIT * 2),
        ).fetchall()
    items: list[dict] = []
    for row in rows:
        if row["name"] is None:
            continue
        if row["mention_count"] < _SUMMARY_MIN_MENTIONS and row["confidence"] < _SUMMARY_MIN_CONFIDENCE:
            continue
        description = (row["description"] or "").strip()
        if len(description) > _SUMMARY_DESC_CHARS:
            description = description[:_SUMMARY_DESC_CHARS] + "…"
        items.append(
            {
                "kind": row["kind"],
                "id": row["id"],
                "name": row["name"],
                "description": description,
                "mention_count": row["mention_count"],
            }
        )
        if len(items) >= _SUMMARY_LIMIT:
            break
    return items


def _render_object_summary(lines: list[str], topic: str, store: SemanticStore) -> None:
    """Render the top-object summary for one topic section."""
    items = _topic_object_summary(store, topic)
    if not items:
        lines.extend(["暂无高频语义对象。", ""])
        return
    lines.extend(["**高频对象：**", ""])
    for item in items:
        kind_label = "概念" if item["kind"] == "concept" else "实体"
        description = f"：{item['description']}" if item["description"] else ""
        lines.append(f"- [{kind_label}] **{item['name']}**{description}（提及 {item['mention_count']} 次）")
    lines.append("")


def build_topic_wiki_page(store: SemanticStore, topic: str) -> dict:
    """Return a page preview and its source snapshot.

    A top-level topic yields the full merged page (all descendant topics become
    nested sections). A sub-topic yields only its own section (preview mode);
    the returned `target` always points at the merged top-level file.
    """
    top = top_level_topic(topic)
    state = build_topic_state(store, top)
    target = _target_path(store, top)
    generated_at = datetime.now(timezone.utc).isoformat()
    # Every topic under `top` keeps a section, mirroring the previous
    # one-file-per-topic behaviour.
    prefix = top + TOPIC_SEP
    with store.connect() as conn:
        topic_rows = conn.execute(
            """SELECT DISTINCT topic FROM documents
               WHERE (topic = ? OR instr(topic, ?) = 1) AND topic != ''""",
            (top, prefix),
        ).fetchall()
    topics = sorted(
        {row["topic"] for row in topic_rows} or {top},
        key=lambda key: (key.count(TOPIC_SEP), key),
    )
    is_full_page = top == topic
    if not is_full_page:
        sub_prefix = topic + TOPIC_SEP
        topics = [key for key in topics if key == topic or key.startswith(sub_prefix)]
        base_depth = topic.count(TOPIC_SEP)
    page_hash = content_hash(state["input_hash"])
    lines: list[str] = []
    if is_full_page:
        lines.extend(
            [
                "---",
                f'title: "{top} · 语义知识"',
                f"topic: {top}",
                "semantic_page: true",
                f"generated_at: {generated_at}",
                f"input_hash: {page_hash}",
                "---",
                "",
                f"# {top}",
                "",
                "> 本页由语义编译的高频实体/概念自动物化；对象详情见语义工作台。",
                "",
            ]
        )
    for key in topics:
        if is_full_page:
            depth = key.count(TOPIC_SEP)
        else:
            depth = key.count(TOPIC_SEP) - base_depth
        label = key.split(TOPIC_SEP)[-1].strip() if key.count(TOPIC_SEP) else key
        heading = "#" * (depth + 1)
        lines.extend([f"{heading} {label}", ""])
        if not is_full_page and key.count(TOPIC_SEP):
            lines.extend([f"> 主题：{key}", ""])
        _render_object_summary(lines, key, store)
    return {
        "topic": top,
        "target": target,
        "content": "\n".join(lines).rstrip() + "\n",
        "input_hash": page_hash if is_full_page else None,
        "state": state,
    }


def materialize_topic_wiki_page(store: SemanticStore, topic: str) -> Path:
    """Write the merged page for the topic's top-level group (atomic replace)."""
    top = top_level_topic(topic)
    page = build_topic_wiki_page(store, top)
    target: Path = page["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=target.parent, prefix=f".{target.stem}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(page["content"])
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    source_ids = {item["id"] for item in page["state"]["documents"]} | {
        item["id"] for item in page["state"]["objects"]
    }
    store.replace_view_dependencies(
        view_id=stable_id("semantic_wiki", top.casefold()),
        view_kind="semantic_wiki",
        input_hash=page["input_hash"],
        source_ids=source_ids,
    )
    return target
