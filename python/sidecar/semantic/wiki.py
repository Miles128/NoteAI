"""Quality-gated, evidence-linked semantic Wiki pages for topic states."""

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


def _safe_segment(value: str) -> str:
    cleaned = _UNSAFE_PATH.sub("_", value.strip()).strip(". ")
    return cleaned or "未命名主题"


def _target_path(store: SemanticStore, topic: str) -> Path:
    parts = [_safe_segment(part) for part in topic.split(TOPIC_SEP) if part.strip()]
    if not parts:
        parts = ["未命名主题"]
    return store.workspace / ABSTRACT_FOLDER / "semantic" / Path(*parts[:-1]) / f"{parts[-1]}_语义.md"


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


def build_topic_wiki_page(store: SemanticStore, topic: str) -> dict:
    """Return a read-only page preview and its quality-gated source snapshot."""
    state = build_topic_state(store, topic)
    conflicted = _pending_conflicted_claim_ids(store)
    claims = [claim for claim in state["claims"] if claim["id"] not in conflicted]
    blocked = sorted({claim["id"] for claim in state["claims"]} & conflicted)
    target = _target_path(store, topic)
    generated_at = datetime.now(timezone.utc).isoformat()
    page_hash = content_hash(
        json.dumps(
            {"topic_state": state["input_hash"], "blocked_claims": blocked},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    lines = [
        "---",
        f'title: "{topic} · 语义知识"',
        f"topic: {topic}",
        "semantic_page: true",
        f"generated_at: {generated_at}",
        f"input_hash: {page_hash}",
        "---",
        "",
        f"# {topic}",
        "",
        "> 本页由通过质量门禁的语义命题自动物化；每项均保留原始 Notes 证据。",
        "",
    ]
    if blocked:
        lines.extend([
            "## 待审核冲突",
            "",
            f"有 {len(blocked)} 条命题因关联待审核冲突，暂不发布到本页。",
            "",
        ])
    conclusion = [claim for claim in claims if claim["claim_type"] == "conclusion"]
    hypothesis = [claim for claim in claims if claim["claim_type"] == "hypothesis"]
    for title, group, prefix in (("已发布结论", conclusion, ""), ("待验证假设", hypothesis, "**假设：** ")):
        lines.extend([f"## {title}", ""])
        if not group:
            lines.extend(["暂无符合质量门禁的命题。", ""])
            continue
        for claim in group:
            scope = f"（适用范围：{claim['scope']}）" if claim["scope"] else ""
            lines.extend([f"- {prefix}{claim['statement']}{scope}"])
            for evidence in claim["evidence"]:
                heading = " › ".join(evidence["heading_path"])
                source = evidence["document_path"] + (f" · {heading}" if heading else "")
                relative = os.path.relpath(store.workspace / evidence["document_path"], target.parent)
                lines.append(f"  - 证据：[ {source} ]({relative.replace(os.sep, '/')})")
        lines.append("")
    return {
        "topic": topic,
        "target": target,
        "content": "\n".join(lines).rstrip() + "\n",
        "input_hash": page_hash,
        "state": state,
        "claims": claims,
        "blocked_claim_ids": blocked,
    }


def materialize_topic_wiki_page(store: SemanticStore, topic: str) -> Path:
    page = build_topic_wiki_page(store, topic)
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
        claim["id"] for claim in page["claims"]
    } | {
        evidence["block_id"]
        for claim in page["claims"]
        for evidence in claim["evidence"]
    }
    store.replace_view_dependencies(
        view_id=stable_id("semantic_wiki", topic.casefold()),
        view_kind="semantic_wiki",
        input_hash=page["input_hash"],
        source_ids=source_ids,
    )
    return target
