"""笔记合并建议分析器。

基于已建立的 RAG 索引（zvec 向量集合）与语义库（semantic.db）对笔记做
相似度分析，输出笔记级合并候选与分级建议。只读分析，不修改任何数据。

分级语义：
- A 级（同源双稿）：向量相似度极高（>= 0.96）且结构对应，几乎可判定为同源
- B 级（深度重叠）：高相似（>= 0.92），可能为综述与展开稿关系
- C 级（主题关联）：中等相似（>= 0.85），仅作参考
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from config import config
from utils.logger import logger

# 分级阈值
_A_LEVEL = 0.96
_B_LEVEL = 0.92
_C_LEVEL = 0.85
# 单次分析最多处理的笔记数（超出取前 N 篇），控制计算量
_MAX_NOTES = 400
# 返回候选上限
_MAX_SUGGESTIONS = 60


def _load_file_vectors() -> tuple[list[str], np.ndarray | None]:
    """从 RAG 索引读取全部笔记的平均向量。

    返回 (rel_paths, matrix)，matrix 为归一化后的 (N, 512)。
    索引未建立或不可用时返回 (files, None)。
    """
    workspace = config.workspace_path
    if not workspace:
        return [], None
    try:
        from sidecar.rag.index import _get_collection

        ws = str(Path(workspace))
        collection = _get_collection(ws)
        meta_path = Path(workspace) / ".noteai" / "rag_index" / "metadata.json"
        if not meta_path.exists():
            return [], None
        import json

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        files: dict[str, list[str]] = metadata.get("files", {})
        if not files:
            return [], None

        all_ids = [cid for cids in files.values() for cid in cids]
        vectors: dict[str, np.ndarray] = {}
        batch_size = 500
        for i in range(0, len(all_ids), batch_size):
            batch = all_ids[i : i + batch_size]
            try:
                docs = collection.fetch(batch, include_vector=True)
            except Exception:
                continue
            for cid in batch:
                doc = docs.get(cid)
                if doc is None:
                    continue
                try:
                    vectors[cid] = np.asarray(doc.vector("dense"), dtype=np.float32)
                except Exception:
                    continue
        if not vectors:
            return [], None

        file_vec: dict[str, np.ndarray] = {}
        for rel, cids in files.items():
            vs = [vectors[c] for c in cids if c in vectors]
            if vs:
                file_vec[rel] = np.mean(np.stack(vs), axis=0)
        if not file_vec:
            return [], None

        rels = list(file_vec.keys())[:_MAX_NOTES]
        mat = np.stack([file_vec[r] for r in rels])
        norm = np.linalg.norm(mat, axis=1, keepdims=True)
        mat = mat / (norm + 1e-9)
        return rels, mat
    except Exception as e:
        logger.warning(f"[note_merge_analyzer] 读取向量索引失败: {e}")
        return [], None


def _filter_existing(rels: list[str]) -> list[str]:
    """过滤已不存在（被删除/移动）的文件，避免分析过期索引数据。"""
    workspace = config.workspace_path
    if not workspace:
        return []
    ws = Path(workspace)
    return [r for r in rels if (ws / r).exists()]


def _load_semantic_shares() -> dict[tuple[str, str], int]:
    """从语义库读取文档对的实体/概念共享计数。

    返回 {(rel_a, rel_b): shared_count}，只包含共享 >= 1 的对。
    """
    workspace = config.workspace_path
    if not workspace:
        return {}
    store_path = Path(workspace) / ".noteai" / "compiler" / "semantic.db"
    if not store_path.exists():
        return {}
    try:
        import sqlite3

        conn = sqlite3.connect(store_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """SELECT d1.path AS a, d2.path AS b, count(DISTINCT m1.object_id) AS shared
                   FROM semantic_mentions m1
                   JOIN blocks b1 ON b1.id = m1.block_id
                   JOIN documents d1 ON d1.id = b1.document_id
                   JOIN semantic_mentions m2 ON m2.object_id = m1.object_id
                   JOIN blocks b2 ON b2.id = m2.block_id
                   JOIN documents d2 ON d2.id = b2.document_id
                   WHERE d1.path < d2.path
                     AND m1.object_kind = m2.object_kind
                   GROUP BY d1.path, d2.path"""
            ).fetchall()
        finally:
            conn.close()
        return {(row["a"], row["b"]): int(row["shared"]) for row in rows}
    except Exception as e:
        logger.warning(f"[note_merge_analyzer] 读取语义共享失败: {e}")
        return {}


def get_note_merge_suggestions(
    *,
    min_score: float = _B_LEVEL,
    max_results: int = _MAX_SUGGESTIONS,
) -> dict[str, Any]:
    """生成笔记合并建议。

    同时利用 RAG 索引（向量相似度）与语义库（实体/概念共享）：
    - 向量相似度 >= min_score 的笔记对进入候选
    - 按相似度排序输出，附带语义共享计数与分级
    - 任一数据源不可用则优雅降级（只输出可用部分）
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "suggestions": []}

    rels, mat = _load_file_vectors()
    semantic = _load_semantic_shares()

    if mat is None:
        return {
            "success": False,
            "message": "RAG 索引尚未建立，请先完成索引构建",
            "suggestions": [],
        }

    # 过滤索引中已不存在的文件（删除/移动后索引未及时更新的过期条目）
    existing = _filter_existing(rels)
    stale_count = len(rels) - len(existing)
    if len(existing) < 2:
        return {
            "success": False,
            "message": "索引中的有效笔记不足",
            "suggestions": [],
        }
    idx_map = {r: i for i, r in enumerate(rels)}
    mat = mat[[idx_map[r] for r in existing]]
    rels = existing

    try:
        sim = mat @ mat.T
        np.fill_diagonal(sim, 0)
    except Exception as e:
        return {"success": False, "message": f"相似度计算失败: {e}", "suggestions": []}

    suggestions: list[dict[str, Any]] = []
    for i in range(len(rels)):
        for j in range(i + 1, len(rels)):
            score = float(sim[i, j])
            if score < min_score:
                continue
            a, b = rels[i], rels[j]
            shared = semantic.get((a, b), semantic.get((b, a), 0))
            if score >= _A_LEVEL:
                level = "A"
            elif score >= _B_LEVEL:
                level = "B"
            else:
                level = "C"
            suggestions.append(
                {
                    "file_a": a,
                    "file_b": b,
                    "score": round(score, 4),
                    "level": level,
                    "shared_objects": shared,
                }
            )

    suggestions.sort(key=lambda s: (-(1 if s["level"] == "A" else 0 if s["level"] == "B" else 2), -s["score"]))
    suggestions = suggestions[:max_results]

    return {
        "success": True,
        "total": len(suggestions),
        "has_index": mat is not None,
        "has_semantics": bool(semantic),
        "stale_count": stale_count,
        "suggestions": suggestions,
    }


def is_index_ready() -> bool:
    """RAG 索引是否已建立（供前端决定是否展示合并建议入口）。"""
    workspace = config.workspace_path
    if not workspace:
        return False
    manifest = Path(workspace) / ".noteai" / "rag_index" / "manifest.json"
    return manifest.exists()


def merge_suggested_notes(
    file_paths: list[str],
    *,
    title: str = "",
    delete_authorized: bool = False,
) -> dict[str, Any]:
    """执行笔记合并：复用既有 merge_note_group 的 LLM 整合逻辑。

    合并后同步处理 .links.json（指向被删副稿的链接重定向到整合稿）。
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}
    if not 2 <= len(file_paths) <= 5:
        return {"success": False, "message": "一次只能整合 2–5 篇笔记"}

    try:
        from sidecar.duplicate_review import merge_note_group

        result = merge_note_group(
            workspace,
            list(file_paths),
            title,
            delete_authorized=delete_authorized,
        )
    except Exception as e:
        logger.warning(f"[note_merge_analyzer] 合并失败: {e}")
        return {"success": False, "message": f"合并失败: {e}"}

    if not result.get("success"):
        return result

    # 链接重定向：被删除的副稿 → 整合稿
    output = str(result.get("output_path") or "")
    deleted = [str(p) for p in (result.get("deleted") or [])]
    if output and deleted:
        _redirect_links(deleted, output)

    return result


def _redirect_links(old_paths: list[str], new_path: str) -> None:
    """把 .links.json 中指向已删除文件的链接重定向到新整合稿。"""
    workspace = config.workspace_path
    if not workspace:
        return
    links_path = Path(workspace) / ".links.json"
    if not links_path.exists():
        return
    try:
        import json

        data = json.loads(links_path.read_text(encoding="utf-8"))
        changed = 0
        for link in data.get("links", []):
            for key in ("from", "to"):
                if link.get(key) in old_paths:
                    link[key] = new_path
                    changed += 1
        if changed:
            tmp = links_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(links_path)
            logger.info(f"[note_merge_analyzer] 合并后链接重定向 {changed} 条 -> {new_path}")
    except Exception as e:
        logger.warning(f"[note_merge_analyzer] 链接重定向失败: {e}")
