"""
双向链接索引引擎

两阶段发现：
1. 本地粗筛：同 topic / 共享 tag / 文件名 token 重叠 → 候选对
2. AI 精判：批处理候选对，LLM 判断是否内容相关

存储：workspace/.links.json
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from config import config, is_ignored_dir
from prompts import CROSS_REF_LLM_PROMPT, LINK_PAIR_JUDGE_PROMPT
from utils.logger import logger
from utils.text_utils import (
    _is_generic_word,
    _is_meaningful_tag,
    _normalize_for_match,
    parse_frontmatter,
)
from utils.text_utils import (
    tokenize as tokenize_text,
)

_VECTOR_SEARCH_COOLDOWN_SECONDS = 60
_vector_search_disabled_until: float = 0.0

# 工作区文件元数据缓存：{workspace: {rel_path: (mtime, meta)}}
_file_meta_cache: dict[str, dict[str, tuple[float, dict[str, Any] | None]]] = {}
_meta_cache_lock = threading.Lock()


def _get_links_path() -> Path | None:
    ws = config.workspace_path
    if not ws:
        return None
    return Path(ws) / ".links.json"


def _extract_json_array(text: str) -> list[Any] | None:
    """从 LLM 响应中提取 JSON 数组；先尝试完整解析，再寻找最外层平衡 [...]。"""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]":
            if depth > 0:
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        return json.loads(text[start : i + 1])
                    except Exception:
                        pass
    return None


def _directed_link_key(from_path: str, to_path: str) -> tuple[str, str]:
    """有向链接的唯一键。A->B 与 B->A 是两条不同的链接。"""
    return (from_path, to_path)


def _is_self_link(from_path: str, to_path: str) -> bool:
    """自引用检查：同一文件的链接不存储。"""
    return from_path == to_path


def _dedupe_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按有向 from/to 去重，保留第一次出现且优先保留 confirmed 状态；同时丢弃自引用。"""
    seen: dict[tuple[str, str], int] = {}
    out: list[dict[str, Any]] = []
    dropped_self = 0
    for link in links:
        from_path = link.get("from", "")
        to_path = link.get("to", "")
        if _is_self_link(from_path, to_path):
            dropped_self += 1
            continue
        key = _directed_link_key(from_path, to_path)
        if key in seen:
            idx = seen[key]
            existing = out[idx]
            if existing.get("status") != "confirmed" and link.get("status") == "confirmed":
                out[idx] = link
            continue
        seen[key] = len(out)
        out.append(link)
    if dropped_self:
        logger.info(f"[link_indexer] 清理 {dropped_self} 条自引用链接")
    return out


def load_links() -> dict[str, Any]:
    path = _get_links_path()
    if not path or not path.exists():
        return {"links": [], "last_scan": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"[link_indexer] 读取 .links.json 失败: {e}")
        return {"links": [], "last_scan": None}

    links = data.get("links", []) or []
    deduped = _dedupe_links(links)
    if len(deduped) < len(links):
        logger.info(f"[link_indexer] 清理 {len(links) - len(deduped)} 条重复/自引用链接")
        data["links"] = deduped
        save_links(data)
    return data


def save_links(data: dict[str, Any]) -> bool:
    path = _get_links_path()
    if not path:
        return False
    try:
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
        return True
    except Exception as e:
        logger.warning(f"[link_indexer] 保存 .links.json 失败: {e}")
        return False


def cleanup_stale_links() -> int:
    workspace = config.workspace_path
    if not workspace:
        return 0
    data = load_links()
    links = data.get("links", [])
    if not links:
        return 0
    ws = Path(workspace)
    original_count = len(links)
    valid = []
    auto_confirmed = 0
    for link in links:
        from_path = link.get("from", "")
        to_path = link.get("to", "")
        from_full = ws / from_path if not Path(from_path).is_absolute() else Path(from_path)
        to_full = ws / to_path if not Path(to_path).is_absolute() else Path(to_path)
        if not from_full.exists() or not to_full.exists():
            logger.info(f"[link_indexer] 清理无效链接: {from_path} -> {to_path}")
            continue
        if link.get("status") == "pending":
            from_topic = _read_file_topic(from_full)
            to_topic = _read_file_topic(to_full)
            if from_topic and from_topic == to_topic:
                link["status"] = "confirmed"
                auto_confirmed += 1
                logger.info(f"[link_indexer] 自动确认链接: {from_path} -> {to_path} (主题: {from_topic})")
        valid.append(link)
    changed = (original_count - len(valid)) + auto_confirmed
    if changed > 0:
        data["links"] = valid
        save_links(data)
    return changed


def _title_mentioned_in_text(title: str, body: str) -> bool:
    if not title or not body:
        return False
    norm_title = _normalize_for_match(title)
    if len(norm_title) < 2:
        return False
    norm_body = _normalize_for_match(body)
    return norm_title in norm_body


def _link_key(from_path: str, to_path: str) -> tuple[str, str]:
    """外部去重使用的有向键：方向不同视为不同链接，自引用返回 None 表示无效。"""
    if _is_self_link(from_path, to_path):
        return None
    return _directed_link_key(from_path, to_path)


def suggest_links_for_file(file_path: str, *, max_suggestions: int = 8) -> dict[str, Any]:
    """After save: local heuristics → pending links (same topic / title mention)."""
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "added": 0}

    ws = Path(workspace)
    full = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)
    if not full.exists() or full.suffix.lower() != ".md":
        return {"success": False, "message": "非 Markdown 文件", "added": 0}

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
    existing_keys = {
        k for k in (_link_key(l.get("from", ""), l.get("to", "")) for l in existing.get("links", [])) if k
    }
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
        if source.get("topic") and source["topic"] == other.get("topic"):
            priority = 1
            reason = f"同主题「{source['topic']}」"
        elif _title_mentioned_in_text(other.get("title", ""), body):
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
        "message": f"建议 {added} 条待确认链接" if added else "无新链接建议",
    }


CROSS_REF_MAX = 25  # soft cap when ranking very long candidate lists
CROSS_REF_CANDIDATE_PREVIEW = 40
CROSS_REF_LLM_BATCH_SIZE = 15


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
            qemb.get("lexical_weights") or {},
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
        if not rel or rel == exclude_rel or rel in seen:
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
        if other:
            neighbors.append((other, "已确认链接的邻居"))
    return neighbors


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
            return candidates[:max_links] if max_links > 0 else candidates
        out: list[dict[str, Any]] = []
        for item in picked:
            idx = item.get("id")
            if idx in idx_map:
                row = dict(idx_map[idx])
                row["reason"] = item.get("reason") or row.get("reason", "相关")
                out.append(row)
            if max_links > 0 and len(out) >= max_links:
                break
        return out if out else (candidates[:max_links] if max_links > 0 else candidates)
    except Exception as e:
        logger.warning(f"[link_indexer] cross-ref LLM error: {e}")
        return candidates[:max_links] if max_links > 0 else candidates


def discover_cross_refs_for_file(
    file_path: str,
    *,
    min_links: int = 0,
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
    existing_keys = {
        k for k in (_link_key(l.get("from", ""), l.get("to", "")) for l in existing_links) if k
    }

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

    if source.get("topic"):
        for path, meta in all_metas.items():
            if meta.get("topic") == source["topic"]:
                _add(path, 100.0, f"同主题「{source['topic']}」", True)

    for path, meta in all_metas.items():
        if _title_mentioned_in_text(meta.get("title", ""), body):
            _add(path, 85.0, f"正文提及「{meta['title']}」", False)
        elif _title_mentioned_in_text(source.get("title", ""), meta.get("summary", "")):
            _add(path, 75.0, f"对方摘要提及「{source['title']}」", False)

    src_tags = set(source.get("tags") or [])
    if src_tags:
        for path, meta in all_metas.items():
            shared = src_tags & set(meta.get("tags") or [])
            if shared:
                _add(path, 65.0, f"共享标签「{next(iter(shared))}」", False)

    for path, _score, reason in _vector_search_candidates(source, body, rel):
        _add(path, 60.0 + min(_score, 1.0) * 20.0, reason, False)

    for path, reason in _one_hop_neighbors(rel, existing_links):
        _add(path, 55.0, reason, False)

    ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
    if use_llm and len(ranked) > 3:
        picked = _llm_pick_cross_refs(source, body, ranked, max_links=max_links)
    else:
        picked = ranked[:max_links] if max_links > 0 else ranked

    merged = list(existing_links)
    added = 0
    confirmed = 0
    pending = 0
    for row in picked:
        key = _link_key(rel, row["path"])
        if not key or key in existing_keys:
            continue
        auto = bool(row.get("auto_confirm") or row.get("score", 0) >= 90.0)
        if use_llm:
            auto = True
        status = "confirmed" if auto else "pending"
        merged.append(
            {
                "from": rel,
                "to": row["path"],
                "reason": row.get("reason", "交叉引用"),
                "status": status,
            }
        )
        existing_keys.add(key)
        added += 1
        if status == "confirmed":
            confirmed += 1
        else:
            pending += 1

    if added:
        save_links({"links": merged, "last_scan": existing.get("last_scan")})

    return {
        "success": True,
        "added": added,
        "confirmed": confirmed,
        "pending": pending,
        "file": rel,
        "candidates": len(ranked),
        "message": f"交叉引用 {added} 条（确认 {confirmed}，待办 {pending}）" if added else "无新交叉引用",
    }


def _read_file_topic(file_path: Path) -> str:
    try:
        text = file_path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(text)
        if not meta:
            return ""
        topic = meta.get("topic")
        if isinstance(topic, list):
            return str(topic[0]).strip() if len(topic) == 1 else ""
        if isinstance(topic, str) and topic.strip():
            return topic.strip()
    except Exception as e:
        logger.error(f"[_read_file_topic] read failed: {e}")
    return ""


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
            if md_file.name.startswith("."):
                continue
            files.append(md_file)
    return files


def _parse_file_meta(md_file: Path) -> dict[str, Any]:
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


def _build_candidate_pairs(metas: list[dict]) -> list[tuple[dict, dict, int]]:
    """
    粗筛候选对，返回 [(meta_a, meta_b, priority)]。
    priority: 1=同topic, 2=共享tag, 3=文件名token重叠
    """
    pairs = []
    seen = set()

    for i in range(len(metas)):
        a = metas[i]
        for j in range(i + 1, len(metas)):
            b = metas[j]
            pair_key = (a["path"], b["path"])
            if pair_key in seen:
                continue

            priority = 0

            # 同 topic
            if a["topic"] and b["topic"] and a["topic"] == b["topic"]:
                priority = 1
            # 共享 tag
            elif a["tags"] and b["tags"]:
                shared = set(a["tags"]) & set(b["tags"])
                if shared:
                    priority = 2
            # 文件名 token 重叠
            else:
                a_tokens = set(
                    _normalize_for_match(t)
                    for t in tokenize_text(a["title"])
                    if _is_meaningful_tag(t) and not _is_generic_word(t)
                )
                b_tokens = set(
                    _normalize_for_match(t)
                    for t in tokenize_text(b["title"])
                    if _is_meaningful_tag(t) and not _is_generic_word(t)
                )
                if len(a_tokens & b_tokens) >= 2:
                    priority = 3

            if priority > 0:
                pairs.append((a, b, priority))
                seen.add(pair_key)

    # 按优先级排序，限制最多 200 对走 AI
    pairs.sort(key=lambda x: x[2])
    return pairs[:200]


def _ask_llm_for_links(candidate_pairs: list[tuple[dict, dict, int]], progress_callback=None) -> list[dict]:
    """
    将候选对批处理发给 LLM，获取确认的链接。
    每次发送最多 15 对。
    """
    if not candidate_pairs:
        return []

    from utils.llm_utils import call_llm_raw, check_api_config

    ok, msg = check_api_config()
    if not ok:
        logger.warning(f"[link_indexer] API not configured: {msg}")
        return []

    all_links = []
    batch_size = CROSS_REF_LLM_BATCH_SIZE

    total_batches = (len(candidate_pairs) + batch_size - 1) // batch_size

    for batch_idx in range(0, len(candidate_pairs), batch_size):
        batch = candidate_pairs[batch_idx : batch_idx + batch_size]

        # 构建 prompt
        lines = []
        idx_map = {}  # local_idx -> (meta_a, meta_b)
        for local_i, (meta_a, meta_b, priority) in enumerate(batch):
            idx_map[local_i + 1] = (meta_a, meta_b)
            lines.append(f"[{local_i + 1}] 《{meta_a['title']}》 | tags: {', '.join(meta_a.get('tags', []))}")
            lines.append(f"    摘要: {meta_a['summary']}")
            lines.append(f"[{local_i + 1}] 《{meta_b['title']}》 | tags: {', '.join(meta_b.get('tags', []))}")
            lines.append(f"    摘要: {meta_b['summary']}")
            lines.append("")

        prompt = LINK_PAIR_JUDGE_PROMPT.format(candidates=chr(10).join(lines))

        try:
            response = call_llm_raw(prompt, temperature=0.3)
            # 提取 JSON
            results = _extract_json_array(response)
            if not results:
                continue
            for item in results:
                pair = item.get("pair", [])
                reason = item.get("reason", "")
                if len(pair) == 2:
                    local_idx = pair[0]
                    if local_idx in idx_map:
                        meta_a, meta_b = idx_map[local_idx]
                        all_links.append(
                            {
                                "from": meta_a["path"],
                                "to": meta_b["path"],
                                "reason": reason,
                                "status": "pending",
                            }
                        )
        except Exception as e:
            logger.warning(f"[link_indexer] LLM batch error: {e}")
            continue

        if progress_callback:
            current_batch = batch_idx // batch_size + 1
            progress_callback(current_batch, total_batches, f"AI 分析中 ({current_batch}/{total_batches})")

    return all_links


def discover_links(progress_callback=None) -> dict[str, Any]:
    """
    运行完整的链接发现流程：
    1. 收集所有文件元数据
    2. 粗筛候选对
    3. AI 精判
    4. 合并到已有链接（保留已确认的，新增 pending）
    5. 存入 .links.json
    """
    workspace = Path(config.workspace_path)
    if not workspace.exists():
        return {"success": False, "message": "工作区不存在"}

    md_files = _iter_md_files(workspace)
    if len(md_files) < 2:
        return {"success": False, "message": "文件数量不足（至少需要2个）"}

    # Step 1: 提取元数据（使用 mtime 缓存，避免每次全量解析）
    if progress_callback:
        progress_callback(0, 3, "正在读取文件元数据...")

    all_metas = _load_all_metas_cached(workspace)
    metas = list(all_metas.values())

    if len(metas) < 2:
        return {"success": False, "message": "可解析的文件数量不足"}

    # Step 2: 粗筛
    if progress_callback:
        progress_callback(1, 3, f"粗筛候选对（共 {len(metas)} 个文件）...")

    candidate_pairs = _build_candidate_pairs(metas)

    if not candidate_pairs:
        return {
            "success": True,
            "new_links": 0,
            "total_links": len(load_links().get("links", [])),
            "message": "未发现候选关联对",
            "files_scanned": len(metas),
        }

    # Step 3: AI 精判
    if progress_callback:
        progress_callback(2, 3, f"AI 分析中（0/{len(candidate_pairs)}）...")

    new_links = _ask_llm_for_links(candidate_pairs, progress_callback)

    if not new_links and candidate_pairs:
        # All LLM calls may have failed; check API
        from utils.llm_utils import check_api_config

        ok, msg = check_api_config()
        if not ok:
            return {"success": False, "message": f"API 未配置: {msg}"}

    # Step 4: 合并到已有链接，新链接直接标记为 confirmed
    existing = load_links()
    existing_links = existing.get("links", [])

    existing_keys = {
        k for k in (_link_key(l.get("from", ""), l.get("to", "")) for l in existing_links) if k
    }

    merged = list(existing_links)
    added_count = 0
    for link in new_links:
        if _is_self_link(link.get("from", ""), link.get("to", "")):
            continue
        key = _link_key(link["from"], link["to"])
        if key and key not in existing_keys:
            link["status"] = "confirmed"
            merged.append(link)
            existing_keys.add(key)
            added_count += 1

    data = {
        "links": merged,
        "last_scan": time.time(),
    }
    save_links(data)

    return {
        "success": True,
        "new_links": added_count,
        "total_links": len(merged),
        "files_scanned": len(metas),
        "candidates_evaluated": len(candidate_pairs),
        "message": f"发现 {added_count} 个新关联",
    }


def get_backlinks(file_path: str) -> dict[str, Any]:
    """获取指定文件的链接；file_path 为空时返回所有链接。"""
    data = load_links()
    all_links = _dedupe_links(data.get("links", []))

    def _to_view(link: dict[str, Any], center_file: str = "") -> dict[str, Any]:
        is_incoming = center_file and link["to"] == center_file
        other = link["from"] if is_incoming else link["to"]
        return {
            "from": link["from"],
            "to": link["to"],
            "file": other,
            "other": other,
            "reason": link.get("reason", ""),
            "status": link.get("status", "pending"),
            "direction": "incoming" if is_incoming else "outgoing",
        }

    if not file_path:
        links = [_to_view(link) for link in all_links]
        return {
            "success": True,
            "file": "",
            "links": links,
            "count": len(links),
        }

    related = [_to_view(link, center_file=file_path) for link in all_links if link["to"] == file_path or link["from"] == file_path]

    return {
        "success": True,
        "file": file_path,
        "links": related,
        "count": len(related),
    }


def confirm_link(from_path: str, to_path: str) -> dict[str, Any]:
    """确认一条有向链接。只匹配精确的 from->to 方向。"""
    if _is_self_link(from_path, to_path):
        return {"success": False, "message": "不能确认自引用链接"}
    data = load_links()
    links = data.get("links", [])
    found = False
    for link in links:
        if link.get("from") == from_path and link.get("to") == to_path:
            link["status"] = "confirmed"
            found = True
            break
    if found:
        save_links(data)
        return {"success": True, "message": "链接已确认"}
    return {"success": False, "message": "链接不存在"}


def reject_link(from_path: str, to_path: str) -> dict[str, Any]:
    """删除一条有向链接。只匹配精确的 from->to 方向。"""
    if _is_self_link(from_path, to_path):
        return {"success": False, "message": "不能删除自引用链接"}
    data = load_links()
    links = data.get("links", [])
    new_links = []
    removed = False
    for link in links:
        if link.get("from") == from_path and link.get("to") == to_path:
            removed = True
            continue
        new_links.append(link)
    if removed:
        data["links"] = new_links
        save_links(data)
        return {"success": True, "message": "链接已删除"}
    return {"success": False, "message": "链接不存在"}


def confirm_all_links() -> dict[str, Any]:
    """一键确认所有 pending 链接"""
    data = load_links()
    links = data.get("links", [])
    count = 0
    for link in links:
        if link.get("status") == "pending":
            link["status"] = "confirmed"
            count += 1
    if count > 0:
        save_links(data)
    return {"success": True, "confirmed": count, "message": f"已确认 {count} 个链接"}
