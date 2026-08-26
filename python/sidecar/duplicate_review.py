"""Review and merge duplicate notes without changing the originals.

合并候选检测（chunk 相似度图 + 语义共享 + 主题候选）与复核/整合执行共处一个模块，
构成唯一的「相似笔记合并」链路。图数据落在 workspace 的 chunk_similarity_graph.json。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import numpy as np

from config.settings import NOTES_FOLDER, WORKSPACE_APP_FOLDER
from sidecar.rag.chunker import chunk_file
from sidecar.text_similarity import body_hash as _body_hash
from utils.helpers import sanitize_filename
from utils.text_utils import parse_frontmatter, write_frontmatter

_STATE_FILE = "duplicate_resolutions.json"


def _root(workspace: str | Path) -> Path:
    return Path(workspace).resolve()


def _safe_note(root: Path, rel: str) -> Path:
    path = (root / rel).resolve()
    notes = (root / NOTES_FOLDER).resolve()
    path.relative_to(notes)
    if path.suffix.lower() != ".md" or not path.is_file():
        raise ValueError("只能处理 Notes/ 下存在的 Markdown 笔记")
    return path


def _pair_key(left: str, right: str) -> str:
    return "|".join(sorted((left, right)))


def _state_path(root: Path) -> Path:
    return root / WORKSPACE_APP_FOLDER / _STATE_FILE


def _load_state(root: Path) -> dict:
    try:
        data = json.loads(_state_path(root).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(root: Path, data: dict) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def is_pair_resolved(root: Path, left: str, right: str, left_body: str, right_body: str) -> bool:
    entry = _load_state(root).get(_pair_key(left, right))
    if not isinstance(entry, dict):
        return False
    direct = entry.get("left_hash") == _body_hash(left_body) and entry.get("right_hash") == _body_hash(right_body)
    reverse = entry.get("left_hash") == _body_hash(right_body) and entry.get("right_hash") == _body_hash(left_body)
    return direct or reverse


def _mark_pair_resolved(root: Path, left: str, right: str, left_body: str, right_body: str) -> None:
    data = _load_state(root)
    data[_pair_key(left, right)] = {
        "left_hash": _body_hash(left_body),
        "right_hash": _body_hash(right_body),
    }
    _save_state(root, data)


def get_duplicate_review(workspace: str | Path, file_path: str, related_file: str) -> dict:
    root = _root(workspace)
    left = _safe_note(root, file_path)
    right = _safe_note(root, related_file)
    left_meta, left_body = parse_frontmatter(left.read_text(encoding="utf-8"))
    right_meta, right_body = parse_frontmatter(right.read_text(encoding="utf-8"))
    return {
        "success": True,
        "file_path": file_path,
        "related_file": related_file,
        "primary": {"title": left.stem, "meta": left_meta or {}, "body": left_body},
        "related": {"title": right.stem, "meta": right_meta or {}, "body": right_body},
        "exact": _body_hash(left_body) == _body_hash(right_body),
    }


def is_merge_group_resolved(root: Path, file_paths: list[str]) -> bool:
    try:
        notes = [_safe_note(root, rel) for rel in file_paths]
        bodies = [parse_frontmatter(note.read_text(encoding="utf-8"))[1] for note in notes]
    except (OSError, ValueError):
        return True
    return all(
        is_pair_resolved(root, file_paths[i], file_paths[j], bodies[i], bodies[j])
        for i in range(len(file_paths))
        for j in range(i + 1, len(file_paths))
    )


def _unique_blocks(primary: str, related: str) -> list[str]:
    existing = {re.sub(r"\s+", "", block).casefold() for block in primary.split("\n\n") if block.strip()}
    return [
        block.strip()
        for block in related.split("\n\n")
        if block.strip() and re.sub(r"\s+", "", block).casefold() not in existing
    ]


def merge_duplicate_notes(
    workspace: str | Path,
    file_path: str,
    related_file: str,
    title: str = "",
) -> dict:
    root = _root(workspace)
    primary = _safe_note(root, file_path)
    related = _safe_note(root, related_file)
    primary_meta, primary_body = parse_frontmatter(primary.read_text(encoding="utf-8"))
    _, related_body = parse_frontmatter(related.read_text(encoding="utf-8"))

    merged_body = primary_body.strip()
    additions = _unique_blocks(primary_body, related_body)
    left_rel = str(primary.relative_to(root))
    right_rel = str(related.relative_to(root))
    if not additions:
        _mark_pair_resolved(root, left_rel, right_rel, primary_body, related_body)
        return {
            "success": True,
            "output_path": left_rel,
            "added_blocks": 0,
            "message": "两篇笔记内容完全相同，已标记为已处理，未创建重复整合稿",
        }
    if additions:
        merged_body = merged_body + "\n\n" + "\n\n".join(additions)

    meta = dict(primary_meta or {})
    for key in ("source", "source_sha256", "origin"):
        meta.pop(key, None)
    output_title = sanitize_filename(title.strip() or f"{primary.stem}（整合）") or f"{primary.stem}-整合"
    output = primary.parent / f"{output_title}.md"
    counter = 1
    while output.exists() and output.resolve() not in {primary.resolve(), related.resolve()}:
        output = primary.parent / f"{output_title}_{counter}.md"
        counter += 1
    if output.resolve() in {primary.resolve(), related.resolve()}:
        return {"success": False, "message": "整合稿名称与原笔记冲突，请换一个名称"}

    output.write_text(write_frontmatter(meta, merged_body), encoding="utf-8")
    _mark_pair_resolved(root, left_rel, right_rel, primary_body, related_body)
    return {
        "success": True,
        "output_path": str(output.relative_to(root)),
        "added_blocks": len(additions),
        "message": "整合稿已创建，原笔记未修改",
    }


def merge_note_group(
    workspace: str | Path,
    file_paths: list[str],
    title: str = "",
    *,
    delete_authorized: bool = False,
) -> dict:
    """Generate one AI synthesis from 2-5 notes; deletion requires this-call authorization."""
    if not 2 <= len(file_paths) <= 5 or len(set(file_paths)) != len(file_paths):
        return {"success": False, "message": "一次只能整合 2–5 篇不同笔记"}
    root = _root(workspace)
    notes = [_safe_note(root, rel) for rel in file_paths]
    parsed = [parse_frontmatter(note.read_text(encoding="utf-8")) for note in notes]
    bodies = [body for _, body in parsed]
    source_blocks = "\n\n".join(
        f'<source index="{index + 1}" path="{file_paths[index]}">\n{body}\n</source>'
        for index, body in enumerate(bodies)
    )
    from prompts import MERGE_NOTES_PROMPT
    from utils.llm_utils import call_llm_raw

    merged_body = call_llm_raw(MERGE_NOTES_PROMPT.format(source_blocks=source_blocks), temperature=0.2).strip()
    if not merged_body:
        return {"success": False, "message": "AI 未返回整合内容"}
    has_conflicts = "观点差异" in merged_body or "待确认冲突" in merged_body
    primary_meta = dict(parsed[0][0] or {})
    for key in ("source", "source_sha256", "origin"):
        primary_meta.pop(key, None)
    primary_meta["merged_from"] = file_paths
    primary_meta["merge_conflicts"] = has_conflicts
    output_title = sanitize_filename(title.strip() or f"{notes[0].stem}（整合）") or f"{notes[0].stem}-整合"
    output = notes[0].parent / f"{output_title}.md"
    counter = 1
    while output.exists() or output.resolve() in {note.resolve() for note in notes}:
        output = notes[0].parent / f"{output_title}_{counter}.md"
        counter += 1
    output.write_text(write_frontmatter(primary_meta, merged_body), encoding="utf-8")

    for left_index, left in enumerate(notes):
        for right_index in range(left_index + 1, len(notes)):
            _mark_pair_resolved(
                root, file_paths[left_index], file_paths[right_index], bodies[left_index], bodies[right_index]
            )

    deleted: list[str] = []
    if delete_authorized and not has_conflicts:
        from send2trash import send2trash

        for note, rel in zip(notes, file_paths, strict=True):
            send2trash(str(note))
            deleted.append(rel)
    return {
        "success": True,
        "output_path": str(output.relative_to(root)),
        "has_conflicts": has_conflicts,
        "deleted": deleted,
        "message": "整合稿已创建" + ("；存在待确认冲突，原笔记已保留" if has_conflicts else ""),
    }


# ── 合并候选检测：chunk 相似度图（原 chunk_similarity.py） ──


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
    from utils.note_scanner import iter_note_files

    chunks: list[dict] = []
    for note in sorted(iter_note_files(root), key=lambda p: str(p.relative_to(root))):
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
