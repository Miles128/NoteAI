"""Sparse whole-vault Chunk similarity graph and explainable merge candidates."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import numpy as np

from config.settings import NOTES_FOLDER, WORKSPACE_APP_FOLDER
from sidecar.rag.chunker import chunk_file

_VERSION = 1
_GRAPH_FILE = "chunk_similarity_graph.json"
_VECTOR_FILE = "chunk_similarity_vectors.npz"

# 笔记合并候选三档阈值（PRD §9.2）：conservative 保守 / balanced 平衡 / aggressive 积极
_MERGE_PRESETS: dict[str, dict[str, float]] = {
    "conservative": {
        "overlap_sim": 0.90,
        "coverage": 0.70,
        "title": 0.86,
        "topic": 0.88,
        "content": 0.74,
        "score": 0.80,
        "topic_name": 0.90,
        "topic_content": 0.76,
    },
    "balanced": {
        "overlap_sim": 0.86,
        "coverage": 0.60,
        "title": 0.82,
        "topic": 0.85,
        "content": 0.68,
        "score": 0.76,
        "topic_name": 0.88,
        "topic_content": 0.72,
    },
    "aggressive": {
        "overlap_sim": 0.80,
        "coverage": 0.50,
        "title": 0.76,
        "topic": 0.80,
        "content": 0.62,
        "score": 0.70,
        "topic_name": 0.84,
        "topic_content": 0.66,
    },
}


def resolve_merge_rules(preset: str = "balanced", overrides: dict | None = None) -> dict[str, float]:
    """Return the effective threshold rules for a merge preset, with optional overrides."""
    effective = dict(_MERGE_PRESETS.get(preset, _MERGE_PRESETS["balanced"]))
    if overrides:
        for key, value in overrides.items():
            if key in effective:
                try:
                    effective[key] = float(value)
                except (TypeError, ValueError):
                    continue
    return effective


def _paths(root: Path) -> tuple[Path, Path]:
    base = root / WORKSPACE_APP_FOLDER
    base.mkdir(parents=True, exist_ok=True)
    return base / _GRAPH_FILE, base / _VECTOR_FILE


def _atomic_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp.replace(path)


def _collect(root: Path) -> list[dict]:
    chunks: list[dict] = []
    notes = root / NOTES_FOLDER
    if not notes.exists():
        return chunks
    for note in sorted(notes.rglob("*.md")):
        rel_parts = note.relative_to(root).parts
        if note.name.startswith(".") or note.name.upper() == "README.MD" or any(p.startswith(".") for p in rel_parts):
            continue
        text = note.read_text(encoding="utf-8")
        for chunk in chunk_file(str(note.relative_to(root)), text):
            body = chunk.get("content") or ""
            chunk["content_hash"] = hashlib.sha256(body.encode()).hexdigest()
            chunk["title"] = note.stem
            chunks.append(chunk)
    return chunks


def _load_previous(root: Path) -> tuple[dict, dict[str, np.ndarray]]:
    graph_path, vector_path = _paths(root)
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        graph = {}
    vectors: dict[str, np.ndarray] = {}
    try:
        packed = np.load(vector_path, allow_pickle=False)
        ids = packed["ids"].astype(str).tolist()
        matrix = packed["vectors"].astype(np.float32)
        vectors = {chunk_id: matrix[index] for index, chunk_id in enumerate(ids)}
    except (OSError, KeyError, ValueError):
        pass
    return graph, vectors


def _load_semantic_shares(root: Path) -> dict[tuple[str, str], int]:
    """从语义库读取文档对的实体/概念共享计数。

    返回 {(rel_a, rel_b): shared_count}，只包含共享 >= 1 的对。
    语义库不存在或不可用时返回空 dict（降级为纯 chunk 相似度）。
    """
    store_path = root / WORKSPACE_APP_FOLDER / "compiler" / "semantic.db"
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
        return {(str(row["a"]), str(row["b"])): int(row["shared"]) for row in rows}
    except Exception as e:
        from utils.logger import logger

        logger.warning(f"[chunk_similarity] 读取语义共享失败: {e}")
        return {}


def _candidate_groups(
    chunks: list[dict],
    edges: list[dict],
    rules: dict[str, float],
    semantic_shares: dict[tuple[str, str], int] | None = None,
) -> list[dict]:
    by_id = {item["id"]: item for item in chunks}
    file_chunks: dict[str, set[str]] = defaultdict(set)
    for item in chunks:
        file_chunks[item["file_path"]].add(item["id"])
    pair_rows: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for edge in edges:
        left = by_id.get(edge["source"])
        right = by_id.get(edge["target"])
        if not left or not right or left["file_path"] == right["file_path"]:
            continue
        key = tuple(sorted((left["file_path"], right["file_path"])))
        pair_rows[key].append(edge)

    qualifying: list[dict] = []
    for (left_path, right_path), rows in pair_rows.items():
        left = next(item for item in chunks if item["file_path"] == left_path)
        right = next(item for item in chunks if item["file_path"] == right_path)
        strong = [row for row in rows if row["similarity"] >= rules["overlap_sim"]]
        matched_left = {
            row["source"] if by_id[row["source"]]["file_path"] == left_path else row["target"] for row in strong
        }
        matched_right = {
            row["source"] if by_id[row["source"]]["file_path"] == right_path else row["target"] for row in strong
        }
        shorter_coverage = min(
            len(matched_left) / max(1, len(file_chunks[left_path])),
            len(matched_right) / max(1, len(file_chunks[right_path])),
        )
        content_score = sum(row["similarity"] for row in rows) / max(1, len(rows))
        title_score = SequenceMatcher(None, left["title"].casefold(), right["title"].casefold()).ratio()
        left_topic = str(left.get("topic") or "")
        right_topic = str(right.get("topic") or "")
        topic_score = (
            1.0
            if left_topic == right_topic and left_topic
            else SequenceMatcher(None, left_topic.casefold(), right_topic.casefold()).ratio()
        )
        # 语义共享信号：两篇笔记共享的实体/概念数（来自 semantic.db）。
        # 同源双稿（综述 vs 展开稿）即使文本不完全重叠，也共享大量实体/概念，
        # 这是 chunk 级相似度之外的互补证据。
        shared_objects = 0
        if semantic_shares:
            shared_objects = semantic_shares.get(
                (left_path, right_path), semantic_shares.get((right_path, left_path), 0)
            )
        score = 0.5 * content_score + 0.25 * title_score + 0.15 * topic_score + 0.1 * shorter_coverage
        # 语义共享加分：共享 >= 3 个实体/概念时逐档加分（0.02/级，上限 0.08）
        semantic_bonus = min(0.08, max(0, (shared_objects - 2) * 0.02))
        score += semantic_bonus
        overlap_rule = bool(strong) and shorter_coverage >= rules["coverage"]
        semantic_rule = (
            title_score >= rules["title"]
            and topic_score >= rules["topic"]
            and content_score >= rules["content"]
            and score >= rules["score"]
        )
        if not (overlap_rule or semantic_rule):
            continue
        qualifying.append(
            {
                "files": [left_path, right_path],
                "score": round(score, 4),
                "content_score": round(content_score, 4),
                "title_score": round(title_score, 4),
                "topic_score": round(topic_score, 4),
                "coverage": round(shorter_coverage, 4),
                "shared_objects": shared_objects,
                "reason": "chunk_overlap" if overlap_rule else "semantic",
                "matches": sorted(rows, key=lambda row: row["similarity"], reverse=True)[:5],
            }
        )

    # Connected candidate pairs become one review group, capped at five files.
    adjacency: dict[str, set[str]] = defaultdict(set)
    for row in qualifying:
        a, b = row["files"]
        adjacency[a].add(b)
        adjacency[b].add(a)
    groups: list[dict] = []
    seen: set[str] = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        stack = [start]
        members: list[str] = []
        while stack and len(members) < 5:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            members.append(current)
            stack.extend(sorted(adjacency[current] - seen, reverse=True))
        rows = [row for row in qualifying if set(row["files"]) <= set(members)]
        groups.append(
            {
                "id": hashlib.sha256("|".join(sorted(members)).encode()).hexdigest()[:16],
                "files": sorted(members),
                "score": round(max((row["score"] for row in rows), default=0.0), 4),
                "reason": "chunk_overlap" if any(row["reason"] == "chunk_overlap" for row in rows) else "semantic",
                "pairs": rows,
            }
        )
    return groups


def _topic_candidates(chunks: list[dict], edges: list[dict], matrix: np.ndarray, rules: dict[str, float]) -> list[dict]:
    topics: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(chunks):
        topic = str(item.get("topic") or "").strip()
        if topic:
            topics[topic].append(index)
    names = sorted(topics)
    if len(names) < 2:
        return []
    from sidecar.rag.embedder import encode_documents

    name_vectors = np.asarray([row["dense_vec"] for row in encode_documents(names)], dtype=np.float32)
    name_vectors /= np.maximum(np.linalg.norm(name_vectors, axis=1, keepdims=True), 1e-12)
    centroids = []
    for name in names:
        centroid = matrix[topics[name]].mean(axis=0)
        centroid /= max(float(np.linalg.norm(centroid)), 1e-12)
        centroids.append(centroid)
    centroid_matrix = np.asarray(centroids, dtype=np.float32)
    rows: list[dict] = []
    for left in range(len(names)):
        for right in range(left + 1, len(names)):
            name_score = float(name_vectors[left] @ name_vectors[right])
            content_score = float(centroid_matrix[left] @ centroid_matrix[right])
            if name_score < rules["topic_name"] or content_score < rules["topic_content"]:
                continue
            rows.append(
                {
                    "topics": [names[left], names[right]],
                    "name_score": round(name_score, 4),
                    "content_score": round(content_score, 4),
                    "score": round(0.55 * name_score + 0.45 * content_score, 4),
                }
            )
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def build_chunk_similarity_graph(
    workspace: str | Path,
    *,
    top_k: int = 6,
    threshold: float = 0.68,
    preset: str = "balanced",
    rules: dict | None = None,
) -> dict:
    root = Path(workspace).resolve()
    effective_rules = resolve_merge_rules(preset, rules)
    chunks = _collect(root)
    previous, old_vectors = _load_previous(root)
    old_meta = {item["id"]: item for item in previous.get("chunks", [])}
    reusable: dict[str, np.ndarray] = {}
    changed: list[dict] = []
    for item in chunks:
        old = old_meta.get(item["id"])
        vector = old_vectors.get(item["id"])
        if old and vector is not None and old.get("content_hash") == item["content_hash"]:
            reusable[item["id"]] = vector
        else:
            changed.append(item)

    if changed:
        from sidecar.rag.embedder import encode_documents

        encoded = encode_documents([item["content"] for item in changed])
        for item, embedding in zip(changed, encoded, strict=True):
            reusable[item["id"]] = np.asarray(embedding["dense_vec"], dtype=np.float32)

    ids = [item["id"] for item in chunks]
    matrix = (
        np.vstack([reusable[chunk_id] for chunk_id in ids]).astype(np.float32)
        if ids
        else np.empty((0, 512), dtype=np.float32)
    )
    if len(matrix):
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.maximum(norms, 1e-12)

    edges_by_pair: dict[tuple[str, str], float] = {}
    batch = 256
    for start in range(0, len(ids), batch):
        scores = matrix[start : start + batch] @ matrix.T
        for offset, row in enumerate(scores):
            index = start + offset
            take = min(top_k + 1, len(ids))
            candidates = np.argpartition(row, -take)[-take:]
            for other in candidates:
                if other == index or float(row[other]) < threshold:
                    continue
                left_id, right_id = sorted((ids[index], ids[int(other)]))
                pair = (left_id, right_id)
                edges_by_pair[pair] = max(edges_by_pair.get(pair, 0.0), float(row[other]))

    edges = [
        {"source": pair[0], "target": pair[1], "similarity": round(score, 4), "distance": round(1 - score, 4)}
        for pair, score in sorted(edges_by_pair.items())
    ]
    stored_chunks = [
        {
            "id": item["id"],
            "file_path": item["file_path"],
            "title": item["title"],
            "topic": item.get("topic") or "",
            "section_title": item.get("section_title") or "",
            "content": (item.get("content") or "")[:500],
            "content_hash": item["content_hash"],
        }
        for item in chunks
    ]
    graph: dict[str, Any] = {
        "version": _VERSION,
        "top_k": top_k,
        "threshold": threshold,
        "preset": preset if preset in _MERGE_PRESETS else "balanced",
        "rules": effective_rules,
        "chunks": stored_chunks,
        "edges": edges,
    }
    semantic_shares = _load_semantic_shares(root)
    graph["candidates"] = _candidate_groups(stored_chunks, edges, effective_rules, semantic_shares)
    graph["topic_candidates"] = _topic_candidates(stored_chunks, edges, matrix, effective_rules) if len(matrix) else []
    graph_path, vector_path = _paths(root)
    _atomic_json(graph_path, graph)
    temp_vectors = vector_path.with_suffix(".tmp.npz")
    np.savez_compressed(temp_vectors, ids=np.asarray(ids), vectors=matrix)
    temp_vectors.replace(vector_path)
    return {
        "success": True,
        "chunk_count": len(ids),
        "edge_count": len(edges),
        "candidate_count": len(graph["candidates"]),
        "topic_candidate_count": len(graph["topic_candidates"]),
    }


def load_chunk_similarity_graph(workspace: str | Path) -> dict:
    graph_path, _ = _paths(Path(workspace).resolve())
    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def graph_view(workspace: str | Path, level: str = "topic", focus: str = "") -> dict:
    graph = load_chunk_similarity_graph(workspace)
    chunks = graph.get("chunks") or []
    edges = graph.get("edges") or []
    if not chunks:
        return {"success": True, "nodes": [], "edges": [], "needs_build": True, "layout": "force"}
    by_id = {item["id"]: item for item in chunks}
    if level == "chunk" and focus:
        selected = {item["id"] for item in chunks if item["file_path"] == focus}
        visible = set(selected)
        for edge in edges:
            if edge["source"] in selected or edge["target"] in selected:
                visible.update((edge["source"], edge["target"]))
        nodes = [
            {**by_id[node_id], "name": by_id[node_id]["section_title"] or by_id[node_id]["title"], "type": "chunk"}
            for node_id in visible
        ]
        shown_edges = [edge for edge in edges if edge["source"] in visible and edge["target"] in visible]
        return {"success": True, "nodes": nodes, "edges": shown_edges, "layout": "force", "level": "chunk"}

    key = "file_path" if level == "note" else "topic"
    groups: dict[str, list[str]] = defaultdict(list)
    for item in chunks:
        if level == "note" and focus and item.get("topic") != focus:
            continue
        groups[str(item.get(key) or "未分类")].append(item["id"])
    node_for = {chunk_id: group for group, members in groups.items() for chunk_id in members}
    aggregate: dict[tuple[str, str], list[float]] = defaultdict(list)
    for edge in edges:
        left = node_for.get(edge["source"])
        right = node_for.get(edge["target"])
        if not left or not right or left == right:
            continue
        left_group, right_group = sorted((left, right))
        aggregate[(left_group, right_group)].append(float(edge["similarity"]))
    node_type = "file" if level == "note" else "topic"
    nodes = [
        {
            "id": name,
            "name": Path(name).stem if level == "note" else name,
            "type": node_type,
            "chunk_count": len(members),
        }
        for name, members in groups.items()
    ]
    shown_edges = [
        {
            "source": pair[0],
            "target": pair[1],
            "similarity": round(max(values), 4),
            "distance": round(1 - max(values), 4),
        }
        for pair, values in aggregate.items()
    ]
    return {"success": True, "nodes": nodes, "edges": shown_edges, "layout": "force", "level": level}
