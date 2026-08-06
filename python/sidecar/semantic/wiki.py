"""Quality-gated, evidence-linked semantic Wiki pages for topic states.

All topic pages are aggregated into one file per top-level topic (e.g.
`AI应用图鉴_语义.md`), with descendant topics rendered as nested sections,
mirroring the WIKI.md bookshelf layout.
"""

from __future__ import annotations

import json
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


def _pending_conflicted_claim_ids(store: SemanticStore) -> set[str]:
    """Read only explicit claim IDs; statement similarity must not suppress knowledge."""
    keys = {"claim_id", "left_claim_id", "right_claim_id"}
    ids: set[str] = set()
    with store.connect() as conn:
        rows = conn.execute(
            """SELECT payload_json FROM review_queue
               WHERE item_kind = 'claim_conflict' AND status = 'pending'"""
        ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value:
                ids.add(value)
        values = payload.get("claim_ids")
        if isinstance(values, list):
            ids.update(value for value in values if isinstance(value, str) and value)
    return ids


def _claim_topic_map(store: SemanticStore, claim_ids: set[str]) -> dict[str, set[str]]:
    """Map each claim id to the topics of its evidence documents."""
    if not claim_ids:
        return {}
    placeholders = ",".join("?" for _ in claim_ids)
    with store.connect() as conn:
        rows = conn.execute(
            f"""SELECT DISTINCT c.id AS claim_id, d.topic AS topic
                FROM claims c
                JOIN evidence e ON e.claim_id = c.id
                JOIN blocks b ON b.id = e.block_id
                JOIN documents d ON d.id = b.document_id
                WHERE c.id IN ({placeholders}) AND d.topic != ''""",
            tuple(sorted(claim_ids)),
        ).fetchall()
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(row["claim_id"], set()).add(row["topic"])
    return result


def _group_claims_by_topic(
    top: str,
    claims: list[dict],
    topic_map: dict[str, set[str]],
) -> dict[str, list[dict]]:
    """Group claims under their deepest matching topic inside `top`'s subtree."""
    prefix = top + TOPIC_SEP
    groups: dict[str, list[dict]] = {}
    for claim in claims:
        topics = topic_map.get(claim["id"], set())
        candidates = [item for item in topics if item == top or item.startswith(prefix)]
        key = max(candidates, key=lambda item: item.count(TOPIC_SEP)) if candidates else top
        groups.setdefault(key, []).append(claim)
    return groups


def _topic_object_summary(store: SemanticStore, topic: str) -> list[dict]:
    """Return top entities/concepts mentioned in a topic's documents.

    Deterministic and free of LLM calls: the summary is a quality-gated,
    frequency-ranked list of extracted objects, so a topic page stays useful
    even before its claims are recovered.
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
    """Render the top-object summary for a topic with no publishable claims."""
    items = _topic_object_summary(store, topic)
    if not items:
        return
    lines.extend(["**高频对象：**", ""])
    for item in items:
        kind_label = "概念" if item["kind"] == "concept" else "实体"
        description = f"：{item['description']}" if item["description"] else ""
        lines.append(f"- [{kind_label}] **{item['name']}**{description}（提及 {item['mention_count']} 次）")
    lines.append("")


def _render_claim_group(
    lines: list[str],
    group: list[dict],
    heading: str,
    target: Path,
    store: SemanticStore,
    topic: str = "",
) -> None:
    conclusion = [claim for claim in group if claim["claim_type"] == "conclusion"]
    hypothesis = [claim for claim in group if claim["claim_type"] == "hypothesis"]
    if not conclusion and not hypothesis and topic:
        # 命题尚未恢复时，用高频对象摘要避免主题页空壳观感。
        _render_object_summary(lines, topic, store)
    for title, claims, prefix in (("已发布结论", conclusion, ""), ("待验证假设", hypothesis, "**假设：** ")):
        lines.extend([f"{heading} {title}", ""])
        if not claims:
            lines.extend(["暂无符合质量门禁的命题。", ""])
            continue
        for claim in claims:
            scope = f"（适用范围：{claim['scope']}）" if claim["scope"] else ""
            lines.extend([f"- {prefix}{claim['statement']}{scope}"])
            for evidence in claim["evidence"]:
                heading_text = " › ".join(evidence["heading_path"])
                source = evidence["document_path"] + (f" · {heading_text}" if heading_text else "")
                relative = os.path.relpath(store.workspace / evidence["document_path"], target.parent)
                lines.append(f"  - 证据：[ {source} ]({relative.replace(os.sep, '/')})")
        lines.append("")


def build_topic_wiki_page(store: SemanticStore, topic: str) -> dict:
    """Return a page preview and its quality-gated source snapshot.

    A top-level topic yields the full merged page (all descendant topics become
    nested sections). A sub-topic yields only its own section (preview mode);
    the returned `target` always points at the merged top-level file.
    """
    top = top_level_topic(topic)
    state = build_topic_state(store, top)
    conflicted = _pending_conflicted_claim_ids(store)
    claims = [claim for claim in state["claims"] if claim["id"] not in conflicted]
    blocked = sorted({claim["id"] for claim in state["claims"]} & conflicted)
    target = _target_path(store, top)
    generated_at = datetime.now(timezone.utc).isoformat()
    topic_map = _claim_topic_map(store, {claim["id"] for claim in claims})
    groups = _group_claims_by_topic(top, claims, topic_map)
    # Every topic under `top` keeps a section even without claims, mirroring the
    # previous one-file-per-topic behaviour (an empty card said "暂无符合质量门禁的命题").
    prefix = top + TOPIC_SEP
    with store.connect() as conn:
        topic_rows = conn.execute(
            """SELECT DISTINCT topic FROM documents
               WHERE (topic = ? OR instr(topic, ?) = 1) AND topic != ''""",
            (top, prefix),
        ).fetchall()
    for row in topic_rows:
        groups.setdefault(row["topic"], [])
    ordered = sorted(groups, key=lambda key: (key.count(TOPIC_SEP), key))
    is_full_page = top == topic
    if not is_full_page:
        sub_prefix = topic + TOPIC_SEP
        ordered = [key for key in ordered if key == topic or key.startswith(sub_prefix)]
        base_depth = topic.count(TOPIC_SEP)
    page_hash = content_hash(
        json.dumps(
            {"topic_state": state["input_hash"], "blocked_claims": blocked},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
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
                "> 本页由通过质量门禁的语义命题自动物化；每项均保留原始 Notes 证据。",
                "",
            ]
        )
        if blocked:
            lines.extend(
                [
                    "## 待审核冲突",
                    "",
                    f"有 {len(blocked)} 条命题因关联待审核冲突，暂不发布到本页。",
                    "",
                ]
            )
    for key in ordered:
        if is_full_page:
            depth = key.count(TOPIC_SEP)
        else:
            depth = key.count(TOPIC_SEP) - base_depth
        label = key.split(TOPIC_SEP)[-1].strip() if key.count(TOPIC_SEP) else key
        heading = "#" * (depth + 1)
        lines.extend([f"{heading} {label}", ""])
        if not is_full_page and key.count(TOPIC_SEP):
            lines.extend([f"> 主题：{key}", ""])
        _render_claim_group(lines, groups[key], f"{heading}#", target, store, topic=key)
    return {
        "topic": top,
        "target": target,
        "content": "\n".join(lines).rstrip() + "\n",
        "input_hash": page_hash if is_full_page else None,
        "state": state,
        "claims": claims,
        "blocked_claim_ids": blocked,
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
    source_ids = (
        {item["id"] for item in page["state"]["documents"]}
        | {claim["id"] for claim in page["claims"]}
        | {evidence["block_id"] for claim in page["claims"] for evidence in claim["evidence"]}
    )
    store.replace_view_dependencies(
        view_id=stable_id("semantic_wiki", top.casefold()),
        view_kind="semantic_wiki",
        input_hash=page["input_hash"],
        source_ids=source_ids,
    )
    return target
