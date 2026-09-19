"""Link discovery: save-time mentions, vector/semantic candidates, LLM batch."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from config import config, is_ignored_dir
from prompts import CROSS_REF_LLM_PROMPT
from utils.links.persist import (
    _directed_link_key,
    _extract_json_array,
    _is_readme_note,
    _is_self_link,
    load_links,
    save_links,
)
from utils.logger import logger
from utils.text_utils import (
    _normalize_for_match,
    parse_frontmatter,
)

_VECTOR_SEARCH_COOLDOWN_SECONDS = 60
_vector_search_disabled_until: float = 0.0

# 工作区文件元数据缓存：{workspace: {rel_path: (mtime, meta)}}
_file_meta_cache: dict[str, dict[str, tuple[float, dict[str, Any] | None]]] = {}
_meta_cache_lock = threading.Lock()


def _title_mentioned_in_text(title: str, body: str) -> bool:
    if not title or not body:
        return False
    norm_title = _normalize_for_match(title)
    if len(norm_title) < 2:
        return False
    norm_body = _normalize_for_match(body)
    return norm_title in norm_body


def _link_key(from_path: str, to_path: str) -> tuple[str, str] | None:
    """外部去重使用的有向键：方向不同视为不同链接，自引用返回 None 表示无效。"""
    if _is_self_link(from_path, to_path):
        return None
    return _directed_link_key(from_path, to_path)


def suggest_links_for_file(file_path: str, *, max_suggestions: int = 8) -> dict[str, Any]:
    """After save: local heuristics → confirmed links (same topic / title mention)."""
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "added": 0}

    ws = Path(workspace)
    full = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)
    if not full.exists() or full.suffix.lower() != ".md":
        return {"success": False, "message": "非 Markdown 文件", "added": 0}
    if _is_readme_note(full):
        return {"success": True, "message": "README 笔记已忽略", "added": 0}

    rel = str(full.relative_to(ws))
    _invalidate_meta_cache(rel)
    source = _parse_file_meta(full)
    if not source:
        return {"success": False, "message": "无法解析文件", "added": 0}

    try:
        _, body = parse_frontmatter(full.read_text(encoding="utf-8"))
    except OSError:
        body = ""

    existing = load_links()
    existing_keys = {k for k in (_link_key(l.get("from", ""), l.get("to", "")) for l in existing.get("links", [])) if k}
    suggestions: list[tuple[dict, int, str]] = []

    all_metas = _load_all_metas_cached(ws)
    for other_rel, other in all_metas.items():
        if other_rel == rel:
            continue
        key = _link_key(rel, other_rel)
        if not key or key in existing_keys:
            continue

        reason = ""
        priority = 0
        # 同主题不连双向链接：仅同属一个主题目录并不是实质关联
        if source.get("topic") and source["topic"] == other.get("topic"):
            continue
        if _title_mentioned_in_text(other.get("title", ""), body):
            priority = 2
            reason = f"正文提及「{other['title']}」"
        elif _title_mentioned_in_text(source.get("title", ""), other.get("summary", "")):
            priority = 3
            reason = f"对方摘要提及「{source['title']}」"

        if priority:
            suggestions.append((other, priority, reason))

    suggestions.sort(key=lambda x: x[1])
    merged = list(existing.get("links", []))
    added = 0
    for other, _prio, reason in suggestions[:max_suggestions]:
        key = _link_key(rel, other["path"])
        if not key or key in existing_keys:
            continue
        # 严格判断：标题提及、摘要提及只是候选信号，一律待人工确认，
        # 不因启发式规则自动放行（同主题已跳过，不在此处生成候选）。
        merged.append(
            {
                "from": rel,
                "to": other["path"],
                "reason": reason,
                "status": "pending",
            }
        )
        existing_keys.add(key)
        added += 1

    if added:
        save_links({"links": merged, "last_scan": existing.get("last_scan")})

    return {
        "success": True,
        "added": added,
        "file": rel,
        "message": f"新增 {added} 条关联" if added else "无新链接建议",
    }


CROSS_REF_MAX = 25  # soft cap when ranking very long candidate lists
CROSS_REF_CANDIDATE_PREVIEW = 40


def _vector_search_candidates(
    source_meta: dict[str, Any],
    body: str,
    exclude_rel: str,
    *,
    limit: int = 30,
) -> list[tuple[str, float, str]]:
    """RAG hybrid search → candidate rel_paths with scores."""
    workspace = config.workspace_path
    if not workspace:
        return []

    query = f"{source_meta.get('title', '')}\n{body[:800]}".strip()
    if not query:
        return []

    global _vector_search_disabled_until
    if time.time() < _vector_search_disabled_until:
        return []

    try:
        from sidecar.rag.embedder import encode_query
        from sidecar.rag.index import hybrid_search

        qemb = encode_query(query)
        if not qemb.get("dense_vec"):
            return []
        hits = hybrid_search(
            workspace,
            qemb["dense_vec"],
            top_k=limit + 5,
        )
    except Exception as e:
        logger.warning(f"[link_indexer] vector search failed, cooling down for {_VECTOR_SEARCH_COOLDOWN_SECONDS}s: {e}")
        _vector_search_disabled_until = time.time() + _VECTOR_SEARCH_COOLDOWN_SECONDS
        return []

    out: list[tuple[str, float, str]] = []
    seen: set[str] = set()
    for hit in hits:
        rel = hit.get("file_path", "")
        if not rel or rel == exclude_rel or rel in seen or _is_readme_note(rel):
            continue
        seen.add(rel)
        score = float(hit.get("score") or hit.get("dense_score") or 0.0)
        out.append((rel, score, "语义相关"))
        if len(out) >= limit:
            break
    return out


def _one_hop_neighbors(rel_path: str, links: list[dict]) -> list[tuple[str, str]]:
    """Confirmed links → 1-hop neighbor paths."""
    neighbors: list[tuple[str, str]] = []
    for link in links:
        if link.get("status") != "confirmed":
            continue
        other = ""
        if link.get("from") == rel_path:
            other = link.get("to", "")
        elif link.get("to") == rel_path:
            other = link.get("from", "")
        if other and not _is_readme_note(other):
            neighbors.append((other, "已确认链接的邻居"))
    return neighbors


#: 两篇文章共享多少实体/概念才算「实质关联」并建议双向链接
_SEMANTIC_SHARE_MIN = 3


def _semantic_share_candidates(
    store: Any,
    rel_path: str,
    all_metas: dict[str, dict[str, Any]],
    links: list[dict],
) -> list[tuple[str, str, float]]:
    """
    通过语义提取的实体/概念共享发现双向关联候选。

    同一批实体/概念在「源与目标」两侧都出现，通常是同一实体的多份资料
    （同主题、同产品、同论文），属于真实的双向引用；共享量越多越可靠。
    返回 [(rel_path, reason, score)]，仅返回双向都有语义证据的候选对。
    """
    try:
        from sidecar.semantic.ids import stable_id

        existing_keys = {k for k in (_link_key(l.get("from", ""), l.get("to", "")) for l in links) if k}
        # 已存在任一方向的边则跳过，避免重复建议
        pending_keys = existing_keys

        out: list[tuple[str, str, float]] = []
        src_id = stable_id("doc", rel_path)
        src_objects = _store_objects_for(store, src_id)
        if not src_objects:
            return out
        src_names = {o["name"] for o in src_objects}
        available = set(all_metas) - {rel_path}
        cache: dict[str, set[str]] = {}
        for other in available:
            key = _link_key(rel_path, other)
            if not key or key in pending_keys:
                continue
            other_id = stable_id("doc", other)
            shared = src_names & _object_names_for(store, cache, other_id)
            # 分成两档：强共享（≥5）高置信；中等（≥3）次之
            if len(shared) >= 5:
                out.append((other, f"共享 {len(shared)} 个实体/概念", 90.0 + min(len(shared), 10)))
            elif len(shared) >= _SEMANTIC_SHARE_MIN:
                out.append((other, f"共享 {len(shared)} 个实体/概念", 70.0 + len(shared)))
        return out
    except Exception as e:
        logger.warning(f"[link_indexer] 语义共享计算失败: {e}")
        return []


def _store_objects_for(store: Any, document_id: str) -> list[dict]:
    try:
        return store.objects_for_document(document_id)
    except Exception:
        return []


def _object_names_for(store: Any, cache: dict[str, set[str]], document_id: str) -> set[str]:
    if document_id not in cache:
        raw = (o.get("name") for o in _store_objects_for(store, document_id))
        names = {name for name in raw if isinstance(name, str) and name.strip()}
        cache[document_id] = names
    return cache[document_id]


#: 全库回填双向链接时，两篇文章共享实体/概念的强阈值
_BIDIRECTIONAL_SHARE_MIN = 6


def backfill_semantic_bidirectional() -> dict[str, Any]:
    """
    全库回填：对「共享大量实体/概念」的文档对建立双向链接。

    仅在两侧（A→B 与 B→A）都尚无任何边时才补（avoid the hub-diameter
    麻团：只把真正多次共同出现的实体对连通，不重复叠加）。
    产出的是 pending，等待人工确认。
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "added": 0}
    ws = Path(workspace)
    try:
        from sidecar.semantic.ids import stable_id
        from sidecar.semantic.store import SemanticStore
    except Exception as e:
        return {"success": False, "message": f"语义库不可用: {e}", "added": 0}

    all_metas = _load_all_metas_cached(ws)
    if len(all_metas) < 2:
        return {"success": False, "message": "可解析文件不足", "added": 0}

    store = SemanticStore(ws)
    names: dict[str, set[str]] = {}
    for rel in all_metas:
        doc_id = stable_id("doc", rel)
        s = _object_names_for(store, names, doc_id)
        # 空集合也要占位（不缓存会反复查库）
        names[rel] = s

    existing = load_links()
    existing_links = existing.get("links", [])
    directed = {k for k in (_link_key(l.get("from", ""), l.get("to", "")) for l in existing_links) if k}

    rels = list(all_metas)
    added = 0
    for i in range(len(rels)):
        a = rels[i]
        a_names = names.get(a) or set()
        if not a_names:
            continue
        for b in rels[i + 1 :]:
            bn = names.get(b) or set()
            shared = a_names & bn
            if len(shared) < _BIDIRECTIONAL_SHARE_MIN:
                continue
            k_ab = _link_key(a, b)
            k_ba = _link_key(b, a)
            if k_ab is None or k_ba is None:
                continue
            if k_ab in directed or k_ba in directed:
                continue
            reason = f"共享 {len(shared)} 个实体/概念"
            existing_links.append({"from": a, "to": b, "reason": reason, "status": "pending"})
            existing_links.append({"from": b, "to": a, "reason": reason, "status": "pending"})
            directed.add(k_ab)
            directed.add(k_ba)
            added += 2

    if added:
        save_links({"links": existing_links, "last_scan": existing.get("last_scan")})
        logger.info(f"[link_indexer] 双向语义回填: 新增 {added} 条")
    return {"success": True, "added": added, "total": len(existing_links)}


def _llm_pick_cross_refs(
    source_meta: dict[str, Any],
    body_excerpt: str,
    candidates: list[dict[str, Any]],
    *,
    max_links: int,
) -> list[dict[str, Any]]:
    if not candidates:
        return []

    from utils.llm_utils import call_llm_raw, check_api_config

    ok, msg = check_api_config()
    if not ok:
        logger.warning(f"[link_indexer] cross-ref LLM skipped: {msg}")
        return candidates[:max_links] if max_links > 0 else candidates

    lines = []
    idx_map: dict[int, dict[str, Any]] = {}
    for i, c in enumerate(candidates[:CROSS_REF_CANDIDATE_PREVIEW], start=1):
        idx_map[i] = c
        lines.append(
            f"[{i}] 《{c.get('title', '')}》 topic={c.get('topic') or '-'} "
            f"tags={','.join(c.get('tags') or [])}\n    {c.get('summary', '')[:200]}"
        )

    prompt = CROSS_REF_LLM_PROMPT.format(
        title=source_meta.get("title", ""),
        summary=body_excerpt[:400],
        candidates=chr(10).join(lines),
    )

    try:
        response = call_llm_raw(prompt, temperature=0.2)
        picked = _extract_json_array(response)
        if picked is None:
            # LLM 不可用时不做任何兜底：宁缺毋滥，不因启发式规则自动放行
            return []
        out: list[dict[str, Any]] = []
        for item in picked:
            idx = item.get("id")
            if idx in idx_map:
                row = dict(idx_map[idx])
                row["reason"] = item.get("reason") or row.get("reason", "相关")
                out.append(row)
            if max_links > 0 and len(out) >= max_links:
                break
        return out
    except Exception as e:
        logger.warning(f"[link_indexer] cross-ref LLM error: {e}")
        return []


def discover_cross_refs_for_file(
    file_path: str,
    *,
    max_links: int = CROSS_REF_MAX,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Suggest outgoing links for one note → stored in workspace/.links.json.

    These are **directional** link records (from → to). Backlinks are derived
    when querying the graph; the engine does not auto-insert [[wikilinks]] into
    note bodies. Link count is quality-driven, not forced to a minimum.
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "added": 0}

    ws = Path(workspace)
    full = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)
    if not full.exists() or full.suffix.lower() != ".md":
        return {"success": False, "message": "非 Markdown 文件", "added": 0}
    if _is_readme_note(full):
        return {"success": True, "message": "README 笔记已忽略", "added": 0}

    rel = str(full.relative_to(ws))

    # 保存后强制刷新当前文件缓存，确保后续读取到最新内容
    _invalidate_meta_cache(rel)

    source = _parse_file_meta(full)
    if not source:
        return {"success": False, "message": "无法解析文件", "added": 0}

    try:
        _, body = parse_frontmatter(full.read_text(encoding="utf-8"))
    except OSError:
        body = ""

    existing = load_links()
    existing_links = existing.get("links", [])
    existing_keys = {k for k in (_link_key(l.get("from", ""), l.get("to", "")) for l in existing_links) if k}

    # 使用 mtime 缓存，避免每次保存都全量解析所有文件
    all_metas = _load_all_metas_cached(ws)

    scored: dict[str, dict[str, Any]] = {}

    def _add(path: str, score: float, reason: str, auto_confirm: bool) -> None:
        if path == rel or path not in all_metas:
            return
        key = _link_key(rel, path)
        if not key or key in existing_keys:
            return
        prev = scored.get(path)
        if prev and prev["score"] >= score:
            return
        scored[path] = {
            "path": path,
            "title": all_metas[path]["title"],
            "topic": all_metas[path].get("topic"),
            "tags": all_metas[path].get("tags") or [],
            "summary": all_metas[path].get("summary", ""),
            "score": score,
            "reason": reason,
            "auto_confirm": auto_confirm,
        }

    # 实体/概念共享：两篇文章共同出现足够的实体/概念，视为实质关联
    _SemanticStore: Any = None
    try:
        from sidecar.semantic.store import SemanticStore as _SemanticStore
    except Exception:  # pragma: no cover - sidecar 依赖不可用时跳过
        _SemanticStore = None  # type: ignore[assignment]

    if _SemanticStore is not None:
        try:
            shared_semantic = _semantic_share_candidates(_SemanticStore(ws), rel, all_metas, existing_links)
            for path, reason, score in shared_semantic:
                _add(path, score, reason, auto_confirm=False)
        except Exception as e:
            logger.warning(f"[link_indexer] 语义共享候选失败: {e}")

    # 同主题不连双向链接：仅同属一个主题目录并不是实质关联，直接跳过

    for path, meta in all_metas.items():
        if _title_mentioned_in_text(meta.get("title", ""), body):
            _add(path, 85.0, f"正文提及「{meta['title']}」", False)
        elif _title_mentioned_in_text(source.get("title", ""), meta.get("summary", "")):
            _add(path, 75.0, f"对方摘要提及「{source['title']}」", False)

    ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
    if use_llm and len(ranked) > 3:
        picked = _llm_pick_cross_refs(source, body, ranked, max_links=max_links)
    else:
        picked = ranked[:max_links] if max_links > 0 else ranked

    merged = list(existing_links)
    added = 0
    confirmed = 0
    for row in picked:
        key = _link_key(rel, row["path"])
        if not key or key in existing_keys:
            continue
        merged.append(
            {
                "from": rel,
                "to": row["path"],
                "reason": row.get("reason", "交叉引用"),
                # 确定性同主题规则直接确认；LLM/弱启发式候选待人工确认
                "status": "confirmed" if row.get("auto_confirm") else "pending",
            }
        )
        existing_keys.add(key)
        added += 1
        if row.get("auto_confirm"):
            confirmed += 1

    if added:
        save_links({"links": merged, "last_scan": existing.get("last_scan")})

    return {
        "success": True,
        "added": added,
        "confirmed": confirmed,
        "pending": 0,
        "file": rel,
        "candidates": len(ranked),
        "message": f"交叉引用 {added} 条（已确认 {confirmed}）" if added else "无新交叉引用",
    }


def _iter_md_files(workspace: Path) -> list[Path]:
    """收集所有 MD 文件（排除隐藏文件和忽略目录）"""
    excluded = {"AI Wiki", ".git", ".obsidian", ".trash", "wiki"}
    files = []
    for folder in workspace.iterdir():
        if not folder.is_dir():
            continue
        if folder.name in excluded or folder.name.startswith("."):
            continue
        if is_ignored_dir(folder.name):
            continue
        for md_file in folder.rglob("*.md"):
            if md_file.name.startswith(".") or _is_readme_note(md_file):
                continue
            files.append(md_file)
    return files


def _parse_file_meta(md_file: Path) -> dict[str, Any] | None:
    if _is_readme_note(md_file):
        return None
    try:
        text = md_file.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"[link_indexer] 无法读取文件 {md_file.name}: {e}")
        return None

    meta, body = parse_frontmatter(text)
    title = md_file.stem
    tags = []
    topic = None

    if meta:
        t = meta.get("title")
        if t and isinstance(t, str):
            title = t
        raw_tags = meta.get("tags", [])
        if isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if t]
        elif isinstance(raw_tags, str) and raw_tags.strip():
            tags = [raw_tags.strip()]
        raw_topic = meta.get("topic")
        if isinstance(raw_topic, str) and raw_topic.strip():
            topic = raw_topic.strip()
    else:
        body = text

    summary = body[:500].replace("\n", " ").strip()
    rel_path = str(md_file.relative_to(Path(config.workspace_path)))

    return {
        "path": rel_path,
        "title": title,
        "tags": tags,
        "topic": topic,
        "summary": summary,
    }


def _load_all_metas_cached(workspace: Path) -> dict[str, dict[str, Any]]:
    """
    增量加载工作区所有 Markdown 元数据。
    按 mtime 缓存，只解析新增或修改的文件；删除不存在的文件缓存。
    """
    ws_str = str(workspace)
    files = _iter_md_files(workspace)
    current: dict[str, tuple[float, dict[str, Any] | None]] = {}

    for md in files:
        try:
            rel = str(md.relative_to(workspace))
            mtime = md.stat().st_mtime
            current[rel] = (mtime, None)  # meta 稍后按需填充
        except (OSError, ValueError):
            continue

    with _meta_cache_lock:
        cache = _file_meta_cache.get(ws_str, {})
        result: dict[str, dict[str, Any]] = {}

        for rel, (mtime, _) in current.items():
            cached = cache.get(rel)
            if cached and abs(cached[0] - mtime) <= 0.5 and cached[1] is not None:
                result[rel] = cached[1]
            else:
                full = workspace / rel
                meta = _parse_file_meta(full)
                if meta:
                    result[rel] = meta
                    cache[rel] = (mtime, meta)

        # 清理已删除文件的缓存
        stale = set(cache.keys()) - set(current.keys())
        for rel in stale:
            cache.pop(rel, None)

        _file_meta_cache[ws_str] = cache
        return result


def _invalidate_meta_cache(rel_path: str) -> None:
    """当单个文件保存后，强制刷新该文件的缓存条目。"""
    ws = config.workspace_path
    if not ws:
        return
    with _meta_cache_lock:
        cache = _file_meta_cache.get(ws)
        if cache and rel_path in cache:
            cache.pop(rel_path, None)
