"""Traceable, atomically published aggregate Entity and Concept pages."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config.constants import ABSTRACT_FOLDER
from sidecar.semantic.ids import content_hash, stable_id
from sidecar.semantic.store import SemanticStore

_COLLECTION_NAMES = {"entity": "实体", "concept": "概念"}


def object_collection_target(store: SemanticStore, kind: str) -> Path:
    """Return the single Markdown target for one semantic object category."""
    try:
        name = _COLLECTION_NAMES[kind]
    except KeyError as exc:
        raise ValueError("unsupported semantic object kind") from exc
    return store.workspace / ABSTRACT_FOLDER / "semantic" / f"{name}.md"


def _load_object(store: SemanticStore, kind: str, object_id: str) -> dict:
    if kind not in _COLLECTION_NAMES:
        raise ValueError("unsupported semantic object kind")
    table = "entities" if kind == "entity" else "concepts"
    with store.connect() as conn:
        obj = conn.execute(
            f"SELECT * FROM {table} WHERE id = ? AND status = 'active'",
            (object_id,),
        ).fetchone()
        if obj is None:
            raise ValueError("semantic object not found")
        sources = list(
            conn.execute(
                """SELECT b.id AS block_id, d.path, b.heading_path_json, b.content
                   FROM semantic_mentions m
                   JOIN blocks b ON b.id = m.block_id
                   JOIN documents d ON d.id = b.document_id
                   WHERE m.object_id = ? AND m.object_kind = ?
                   ORDER BY d.path, b.ordinal""",
                (object_id, kind),
            )
        )
        aliases = []
        if kind == "entity":
            aliases = [
                row["alias"]
                for row in conn.execute(
                    "SELECT alias FROM entity_aliases WHERE entity_id = ? ORDER BY alias COLLATE NOCASE",
                    (object_id,),
                )
            ]
        related = []
        for relation in conn.execute(
            """SELECT id, source_id, target_id, relation_type, confidence
               FROM relations WHERE source_id = ? OR target_id = ?
               ORDER BY relation_type, id""",
            (object_id, object_id),
        ):
            other_id = relation["target_id"] if relation["source_id"] == object_id else relation["source_id"]
            other = conn.execute(
                "SELECT canonical_name, 'entity' AS kind FROM entities "
                "WHERE id = ? AND status = 'active' UNION ALL "
                "SELECT canonical_name, 'concept' AS kind FROM concepts "
                "WHERE id = ? AND status = 'active'",
                (other_id, other_id),
            ).fetchone()
            if other:
                related.append(
                    {
                        **dict(relation),
                        "other_id": other_id,
                        "other_name": other["canonical_name"],
                        "other_kind": other["kind"],
                    }
                )
    return {
        "object": dict(obj),
        "sources": [dict(row) for row in sources],
        "aliases": aliases,
        "related": related,
    }


def _object_lines(snapshot: dict, kind: str, target: Path, *, heading_level: int) -> list[str]:
    obj = snapshot["object"]
    sources = snapshot["sources"]
    aliases = snapshot["aliases"]
    related = snapshot["related"]
    prefix = "#" * heading_level
    child = "#" * (heading_level + 1)
    lines = [f"{prefix} {obj['canonical_name']}", ""]
    if kind == "entity":
        lines.extend(
            [
                f"- 类型：{obj['entity_type']}",
                f"- 抽取置信度：{obj['confidence']:.0%}",
                "",
            ]
        )
    if obj["description"]:
        lines.extend([obj["description"], ""])
    if kind == "entity" and aliases:
        lines.extend([f"{child} 别名", "", *[f"- {alias}" for alias in aliases], ""])
    lines.extend([f"{child} 来源", ""])
    for row in sources:
        heading = " › ".join(json.loads(row["heading_path_json"] or "[]"))
        relative = os.path.relpath(target.parents[2] / row["path"], target.parent).replace(os.sep, "/")
        # ``target.parents[2]`` is the workspace for wiki/semantic/*.md.
        lines.append(f"- [{row['path']}{(' · ' + heading) if heading else ''}]({relative})")
    if not sources:
        lines.append("暂无可用来源。")
    lines.extend(["", f"{child} 关联对象", ""])
    if related:
        for relation in related:
            lines.append(
                f"- {relation['relation_type']} · {relation['other_kind']}："
                f"{relation['other_name']}（置信度 {relation['confidence']:.0%}）"
            )
    else:
        lines.append("暂无受控关联。")
    lines.append("")
    return lines


def build_object_page(store: SemanticStore, kind: str, object_id: str) -> dict:
    """Build a read-only preview for one object without creating its own file."""
    snapshot = _load_object(store, kind, object_id)
    obj = snapshot["object"]
    target = object_collection_target(store, kind)
    generated = datetime.now(timezone.utc).isoformat()
    lines = [
        "---",
        f'title: "{obj["canonical_name"]}"',
        f"semantic_kind: {kind}",
        f"generated_at: {generated}",
        "---",
        "",
        *_object_lines(snapshot, kind, target, heading_level=1),
    ]
    content = "\n".join(lines).rstrip() + "\n"
    dependencies = {
        object_id,
        *(row["block_id"] for row in snapshot["sources"]),
        *(row["id"] for row in snapshot["related"]),
    }
    return {
        "target": target,
        "content": content,
        "input_hash": content_hash(content),
        "name": obj["canonical_name"],
        "dependencies": dependencies,
    }


def build_object_collection(store: SemanticStore, kind: str) -> dict:
    """Build the complete, source-backed collection for a category."""
    if kind not in _COLLECTION_NAMES:
        raise ValueError("unsupported semantic object kind")
    table = "entities" if kind == "entity" else "concepts"
    with store.connect() as conn:
        rows = conn.execute(
            f"""SELECT o.id FROM {table} o
                 WHERE o.status = 'active'
                   AND EXISTS (
                       SELECT 1 FROM semantic_mentions m
                       WHERE m.object_id = o.id AND m.object_kind = ?
                   )
                 ORDER BY o.canonical_name COLLATE NOCASE, o.id""",
            (kind,),
        ).fetchall()
    snapshots = [_load_object(store, kind, row["id"]) for row in rows]
    target = object_collection_target(store, kind)
    generated = datetime.now(timezone.utc).isoformat()
    title = _COLLECTION_NAMES[kind]
    body = [
        f"# {title}",
        "",
        f"> 本页聚合当前全部有来源的{title}，共 {len(snapshots)} 条；由语义库自动生成。",
        "",
    ]
    dependencies: set[str] = set()
    for snapshot in snapshots:
        obj = snapshot["object"]
        dependencies.add(obj["id"])
        dependencies.update(row["block_id"] for row in snapshot["sources"])
        dependencies.update(row["id"] for row in snapshot["related"])
        body.extend(_object_lines(snapshot, kind, target, heading_level=2))
    snapshot_hash = content_hash("\n".join(body))
    lines = [
        "---",
        f'title: "{title}"',
        f"semantic_kind: {kind}_collection",
        f"generated_at: {generated}",
        f"input_hash: {snapshot_hash}",
        "---",
        "",
        *body,
    ]
    return {
        "target": target,
        "content": "\n".join(lines).rstrip() + "\n",
        "input_hash": snapshot_hash,
        "dependencies": dependencies,
        "count": len(snapshots),
    }


def _cleanup_legacy_pages(store: SemanticStore, kind: str) -> int:
    """Delete only recognisable generated per-object pages from the old layout."""
    folder = "entities" if kind == "entity" else "concepts"
    legacy_dir = store.workspace / ABSTRACT_FOLDER / "semantic" / folder
    removed = 0
    if not legacy_dir.is_dir():
        return removed
    marker = f"semantic_kind: {kind}"
    for path in legacy_dir.glob("*.md"):
        try:
            header = path.read_text(encoding="utf-8")[:2048]
            if marker not in header:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    try:
        legacy_dir.rmdir()
    except OSError:
        pass
    return removed


def materialize_object_collection(store: SemanticStore, kind: str) -> Path:
    page = build_object_collection(store, kind)
    target: Path = page["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.stem}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(page["content"])
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    except Exception:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    _cleanup_legacy_pages(store, kind)
    with store.connect() as conn:
        conn.execute("DELETE FROM dependencies WHERE target_kind = 'semantic_object_wiki'")
    store.replace_view_dependencies(
        view_id=stable_id("semantic_object_collection", kind),
        view_kind="semantic_object_collection_wiki",
        input_hash=page["input_hash"],
        source_ids=page["dependencies"],
    )
    return target
