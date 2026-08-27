"""Semantic workbench read queries (overview helpers, quality tab, links tab, note context)."""

from __future__ import annotations

import json
from pathlib import Path

from sidecar.semantic.quality import collect_quality_issues
from sidecar.semantic.store import SemanticStore


def empty_overview() -> dict:
    return {
        "documents": 0,
        "blocks": 0,
        "concepts": 0,
        "entities": 0,
        "updated_at": None,
        "source_documents": 0,
        "complete_documents": 0,
        "partial_documents": 0,
        "pending_documents": 0,
        "uncompiled_documents": 0,
    }


def quality_tab(store: SemanticStore, params: dict, *, page: tuple[int, int]) -> dict:
    query = str(params.get("query", "") or "").strip().casefold()
    status = str(params.get("status", "pending") or "pending")
    if status not in {"pending", "reviewed", "all"}:
        status = "pending"
    issues = collect_quality_issues(store)
    counts = dict.fromkeys(
        (
            "missing_source",
            "isolated",
            "low_confidence",
            "uncontrolled_type",
            "missing_description",
            "dangling_relation",
            "alias_conflict",
            "duplicate_candidate",
            "cross_kind_duplicate",
            "unlikely_entity_name",
        ),
        0,
    )
    for issue in issues:
        if issue["status"] == "pending":
            counts[issue["rule"]] += 1
    filtered = [
        issue
        for issue in issues
        if (status == "all" or issue["status"] == status)
        and (
            not query
            or query in f"{issue['entity_name']} {issue['reason']} {' '.join(issue['candidate_names'])}".casefold()
        )
    ]
    limit, offset = page
    return {
        "success": True,
        "tab": "quality",
        "items": filtered[offset : offset + limit],
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "status": status,
        "counts": counts,
    }


def links_tab(workspace: str, params: dict, *, page: tuple[int, int]) -> dict:
    path = Path(workspace) / ".links.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"links": []}
    except (OSError, json.JSONDecodeError) as exc:
        return {"success": False, "message": f"读取链接索引失败: {exc}"}
    status = str(params.get("status", "all") or "all")
    query = str(params.get("query", "") or "").strip().casefold()
    raw_links = data.get("links", []) or []
    directed_pairs = {(str(item.get("from", "") or ""), str(item.get("to", "") or "")) for item in raw_links}
    links = []
    seen = set()
    for raw in raw_links:
        source = str(raw.get("from", "") or "")
        target = str(raw.get("to", "") or "")
        key = (source, target)
        if not source or not target or source == target or key in seen:
            continue
        seen.add(key)
        item_status = str(raw.get("status", "confirmed") or "confirmed")
        if status != "all" and item_status != status:
            continue
        haystack = f"{source} {target} {raw.get('reason', '')}".casefold()
        if query and query not in haystack:
            continue
        reverse = (target, source) in directed_pairs
        links.append({**raw, "from": source, "to": target, "status": item_status, "has_reverse": reverse})
    limit, offset = page
    total = len(links)
    return {
        "success": True,
        "tab": "links",
        "items": links[offset : offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
        "last_scan": data.get("last_scan"),
    }


def note_semantic_context(store: SemanticStore, path: str) -> dict:
    path = path.replace("\\", "/")
    if not path or not store.path.exists():
        return {"success": True, "entities": [], "concepts": [], "relations": []}
    with store.connect() as conn:
        doc = conn.execute("SELECT id FROM documents WHERE path = ?", (path,)).fetchone()
        if doc is None:
            return {"success": True, "entities": [], "concepts": [], "relations": []}

        def objects(table, kind):
            return [
                dict(row)
                for row in conn.execute(
                    f"""SELECT DISTINCT o.id, o.canonical_name, o.description FROM {table} o
                    JOIN semantic_mentions m ON m.object_id = o.id AND m.object_kind = ?
                    JOIN blocks b ON b.id = m.block_id WHERE b.document_id = ? AND o.status = 'active'
                    ORDER BY o.canonical_name""",
                    (kind, doc["id"]),
                )
            ]

        entities = objects("entities", "entity")
        concepts = objects("concepts", "concept")
        labels = {item["id"]: item["canonical_name"] for item in [*entities, *concepts]}
        relations = []
        for row in conn.execute(
            """SELECT DISTINCT r.id, r.source_id, r.target_id, r.relation_type, r.confidence
               FROM relations r JOIN blocks b ON b.id = r.block_id
               WHERE b.document_id = ? ORDER BY r.relation_type, r.id""",
            (doc["id"],),
        ):
            if row["source_id"] in labels and row["target_id"] in labels:
                relations.append(
                    {**dict(row), "source_name": labels[row["source_id"]], "target_name": labels[row["target_id"]]}
                )
    return {"success": True, "entities": entities, "concepts": concepts, "relations": relations}
