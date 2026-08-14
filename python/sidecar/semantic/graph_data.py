"""语义关系星云图数据查询（只读派生）。

从 semantic.db 聚合实体/概念/文档节点与受控共现关系边：
- 对象计数来自 semantic_mentions（按 scope 限定范围）；
- 对象-对象边来自 relations 表（共现关系按共享 block 数加权降噪）；
- 可选对象-文档边（mention 所在文档）。

本模块只读，不触发编译、LLM 或索引重建。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sidecar.semantic.store import SemanticStore

_ENTITY_PREFIX = "e:"
_CONCEPT_PREFIX = "c:"
_DOC_PREFIX = "d:"

_ACTIVE_OBJECT_IDS_SQL = """
SELECT id FROM entities WHERE status = 'active'
UNION
SELECT id FROM concepts WHERE status = 'active'
"""


def _clamp(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _topic_prefix_sql(topic: str) -> tuple[str, list[Any]]:
    """主题路径 → documents.topic 前缀条件（转义 LIKE 通配符）。"""
    escaped = topic.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "d.topic LIKE ? ESCAPE '\\'", [escaped + "%"]


def _scope_filter(scope: str, filter_path: str) -> tuple[str, list[Any]]:
    """返回 scope 限制 SQL（作用在 documents d 上）与参数。"""
    if scope == "topic" and filter_path:
        return _topic_prefix_sql(filter_path)
    if scope == "doc" and filter_path:
        escaped = filter_path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return "(d.path = ? OR d.path LIKE ? ESCAPE '\\')", [filter_path, "%" + escaped + "%"]
    return "1=1", []


def _load_top_objects(conn, scope: str, filter_path: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """按 scope 取 Top N 对象（mentions 计数），返回 (对象列表, kind 映射)。"""
    scope_sql, scope_args = _scope_filter(scope, filter_path)
    rows = conn.execute(
        f"""
        SELECT m.object_id, m.object_kind, COUNT(*) AS cnt
        FROM semantic_mentions m
        JOIN blocks b ON b.id = m.block_id
        JOIN documents d ON d.id = b.document_id
        WHERE m.object_id IN ({_ACTIVE_OBJECT_IDS_SQL})
          AND ({scope_sql})
        GROUP BY m.object_id, m.object_kind
        ORDER BY cnt DESC, m.object_id
        LIMIT ?
        """,
        scope_args + [limit],
    ).fetchall()

    objects: list[dict[str, Any]] = []
    kind_map: dict[str, str] = {}  # object_id -> kind
    for row in rows:
        object_id, kind, cnt = row["object_id"], row["object_kind"], row["cnt"]
        kind_map[object_id] = kind
        prefix = _ENTITY_PREFIX if kind == "entity" else _CONCEPT_PREFIX
        objects.append(
            {
                "id": f"{prefix}{object_id}",
                "object_id": object_id,
                "kind": kind,
                "count": cnt,
            }
        )
    return objects, kind_map


def _attach_object_details(conn, objects: list[dict[str, Any]]) -> None:
    """为对象节点补充名称、类型与描述。"""
    ids = [o["object_id"] for o in objects]
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    entity_rows = {
        row["id"]: row
        for row in conn.execute(
            f"SELECT id, canonical_name, entity_type, description FROM entities WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    }
    concept_rows = {
        row["id"]: row
        for row in conn.execute(
            f"SELECT id, canonical_name, description FROM concepts WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    }
    for obj in objects:
        row = entity_rows.get(obj["object_id"]) or concept_rows.get(obj["object_id"])
        if row is None:
            obj["name"] = obj["object_id"][:10]
            obj["entity_type"] = "other"
            obj["description"] = ""
            continue
        obj["name"] = row["canonical_name"]
        obj["entity_type"] = row["entity_type"] if obj["kind"] == "entity" else ""
        obj["description"] = row["description"]


def _load_relation_edges(conn, objects, min_share: int) -> list[dict[str, Any]]:
    """对象-对象共现边：共享 block 数 >= min_share 的 relations 对。"""
    ids = [o["object_id"] for o in objects]
    if len(ids) < 2:
        return []
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""
        SELECT r.source_id, r.target_id, r.relation_type,
               COUNT(DISTINCT r.block_id) AS weight
        FROM relations r
        WHERE r.source_id IN ({placeholders}) AND r.target_id IN ({placeholders})
        GROUP BY r.source_id, r.target_id, r.relation_type
        HAVING weight >= ?
        """,
        ids + ids + [min_share],
    ).fetchall()
    kind_map = {o["object_id"]: (_ENTITY_PREFIX if o["kind"] == "entity" else _CONCEPT_PREFIX) for o in objects}
    edges = []
    for row in rows:
        src, tgt = row["source_id"], row["target_id"]
        if src == tgt:
            continue
        edges.append(
            {
                "source": f"{kind_map.get(src, '')}{src}",
                "target": f"{kind_map.get(tgt, '')}{tgt}",
                "relation_type": row["relation_type"],
                "weight": row["weight"],
            }
        )
    return edges


def _load_doc_nodes(conn, objects, scope: str, filter_path: str, max_docs: int) -> list[dict[str, Any]]:
    """文档节点：选中对象 mention 所在的文档（Top max_docs，按关联块数）。"""
    ids = [o["object_id"] for o in objects]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    scope_sql, scope_args = _scope_filter(scope, filter_path)
    rows = conn.execute(
        f"""
        SELECT d.id AS doc_id, d.path, d.title,
               COUNT(DISTINCT m.block_id) AS weight
        FROM semantic_mentions m
        JOIN blocks b ON b.id = m.block_id
        JOIN documents d ON d.id = b.document_id
        WHERE m.object_id IN ({placeholders}) AND ({scope_sql})
        GROUP BY d.id
        ORDER BY weight DESC
        LIMIT ?
        """,
        ids + scope_args + [max_docs],
    ).fetchall()
    return [
        {
            "id": f"{_DOC_PREFIX}{r['doc_id']}",
            "object_id": r["doc_id"],
            "kind": "doc",
            "count": r["weight"],
            "name": r["title"] or Path(r["path"]).stem,
            "path": r["path"],
            "entity_type": "",
            "description": "",
        }
        for r in rows
    ]


def _load_document_edges(conn, objects, scope: str, filter_path: str, max_docs: int) -> list[dict[str, Any]]:
    """对象-文档边：选中对象 mention 所在文档（取 Top max_docs）。"""
    ids = [o["object_id"] for o in objects]
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    scope_sql, scope_args = _scope_filter(scope, filter_path)
    rows = conn.execute(
        f"""
        SELECT m.object_id, d.id AS doc_id, d.path, d.title,
               COUNT(DISTINCT m.block_id) AS weight
        FROM semantic_mentions m
        JOIN blocks b ON b.id = m.block_id
        JOIN documents d ON d.id = b.document_id
        WHERE m.object_id IN ({placeholders}) AND ({scope_sql})
        GROUP BY m.object_id, d.id
        ORDER BY weight DESC
        LIMIT ?
        """,
        ids + scope_args + [max_docs],
    ).fetchall()
    kind_map = {o["object_id"]: (_ENTITY_PREFIX if o["kind"] == "entity" else _CONCEPT_PREFIX) for o in objects}
    return [
        {
            "source": f"{kind_map.get(r['object_id'], '')}{r['object_id']}",
            "target": f"{_DOC_PREFIX}{r['doc_id']}",
            "relation_type": "MENTIONED_IN",
            "weight": r["weight"],
        }
        for r in rows
    ]


def get_semantic_graph_data(
    workspace: str | None,
    *,
    scope: str = "all",
    filter_path: str = "",
    limit: int = 80,
    min_share: int = 2,
    include_docs: bool = False,
    max_docs: int = 60,
) -> dict[str, Any]:
    """语义关系星云图数据。

    scope: all | topic | doc；filter_path 为主题路径或文档路径。
    limit: 节点数上限；min_share: 共现边最小共享 block 数；include_docs: 是否含文档节点。
    """
    if not workspace:
        return {"success": False, "message": "工作区未设置"}
    store = SemanticStore(workspace)
    if not store.path.exists():
        return {"success": False, "message": "语义库未初始化"}

    limit = _clamp(limit, 80, 20, 300)
    min_share = _clamp(min_share, 2, 1, 20)
    max_docs = _clamp(max_docs, 60, 10, 200)
    scope = scope if scope in ("all", "topic", "doc") else "all"

    try:
        with store.connect() as conn:
            objects, kind_map = _load_top_objects(conn, scope, filter_path, limit)
            _attach_object_details(conn, objects)
            edges = _load_relation_edges(conn, objects, min_share)
            if include_docs:
                doc_nodes = _load_doc_nodes(conn, objects, scope, filter_path, max_docs)
                objects.extend(doc_nodes)
                edges += _load_document_edges(
                    conn, objects[: len(objects) - len(doc_nodes)], scope, filter_path, max_docs
                )
    except Exception:
        raise

    return {
        "success": True,
        "nodes": objects,
        "edges": edges,
        "meta": {
            "scope": scope,
            "filter": filter_path,
            "object_count": len(objects),
            "edge_count": len(edges),
        },
    }
