"""
双向链接索引引擎

两阶段发现：
1. 本地粗筛：同 topic / 共享 tag / 文件名 token 重叠 → 候选对
2. AI 精判：批处理候选对，LLM 判断是否内容相关

存储：workspace/.links.json
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from config import config, is_ignored_dir
from utils.text_utils import tokenize as tokenize_text, _is_meaningful_tag, _is_generic_word, _normalize_for_match, parse_frontmatter
from utils.logger import logger


def _get_links_path() -> Optional[Path]:
    ws = config.workspace_path
    if not ws:
        return None
    return Path(ws) / ".links.json"


def load_links() -> Dict[str, Any]:
    path = _get_links_path()
    if not path or not path.exists():
        return {"links": [], "last_scan": None}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:
        logger.warning(f"[link_indexer] 读取 .links.json 失败: {e}")
        return {"links": [], "last_scan": None}


def save_links(data: Dict[str, Any]) -> bool:
    path = _get_links_path()
    if not path:
        return False
    try:
        tmp_path = path.with_suffix('.tmp')
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
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
            if from_topic and to_topic:
                link["status"] = "confirmed"
                auto_confirmed += 1
                logger.info(f"[link_indexer] 自动确认链接: {from_path} -> {to_path} (主题: {from_topic} / {to_topic})")
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
    return tuple(sorted([from_path, to_path]))


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
    source = _parse_file_meta(full)
    if not source:
        return {"success": False, "message": "无法解析文件", "added": 0}

    try:
        _, body = parse_frontmatter(full.read_text(encoding="utf-8"))
    except OSError:
        body = ""

    existing = load_links()
    existing_keys = {_link_key(l.get("from", ""), l.get("to", "")) for l in existing.get("links", [])}
    suggestions: list[tuple[dict, int, str]] = []

    for md in _iter_md_files(ws):
        other_rel = str(md.relative_to(ws))
        if other_rel == rel:
            continue
        other = _parse_file_meta(md)
        if not other:
            continue
        key = _link_key(rel, other_rel)
        if key in existing_keys:
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
        if key in existing_keys:
            continue
        merged.append({
            "from": rel,
            "to": other["path"],
            "reason": reason,
            "status": "pending",
        })
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


CROSS_REF_MIN = 0
CROSS_REF_MAX = 25  # soft cap when ranking very long candidate lists


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
        logger.warning(f"[link_indexer] vector search failed: {e}")
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
    for i, c in enumerate(candidates[:40], start=1):
        idx_map[i] = c
        lines.append(
            f"[{i}] 《{c.get('title', '')}》 topic={c.get('topic') or '-'} "
            f"tags={','.join(c.get('tags') or [])}\n    {c.get('summary', '')[:200]}"
        )

    prompt = f"""你是知识库双向链接编辑。源文章：
《{source_meta.get('title', '')}》
摘要：{body_excerpt[:400]}

从下列候选中选出**所有**与源文章有实质关联的笔记（概念重叠、补充、前置知识均可）。数量不设下限或上限，只排除弱相关。
返回 JSON 数组，每项 {{"id": 编号, "reason": "10字内原因"}}。只返回 JSON。

候选：
{chr(10).join(lines)}"""

    try:
        response = call_llm_raw(prompt, temperature=0.2)
        json_match = re.search(r"\[[\s\S]*\]", response)
        if not json_match:
            return candidates[:max_links] if max_links > 0 else candidates
        picked = json.loads(json_match.group(0))
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
    min_links: int = CROSS_REF_MIN,
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
    source = _parse_file_meta(full)
    if not source:
        return {"success": False, "message": "无法解析文件", "added": 0}

    try:
        _, body = parse_frontmatter(full.read_text(encoding="utf-8"))
    except OSError:
        body = ""

    existing = load_links()
    existing_links = existing.get("links", [])
    existing_keys = {_link_key(l.get("from", ""), l.get("to", "")) for l in existing_links}

    all_metas: dict[str, dict[str, Any]] = {}
    for md in _iter_md_files(ws):
        meta = _parse_file_meta(md)
        if meta:
            all_metas[meta["path"]] = meta

    scored: dict[str, dict[str, Any]] = {}

    def _add(path: str, score: float, reason: str, auto_confirm: bool) -> None:
        if path == rel or path not in all_metas:
            return
        key = _link_key(rel, path)
        if key in existing_keys:
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
        if key in existing_keys:
            continue
        auto = bool(row.get("auto_confirm") or row.get("score", 0) >= 90.0)
        if use_llm:
            auto = True
        status = "confirmed" if auto else "pending"
        merged.append({
            "from": rel,
            "to": row["path"],
            "reason": row.get("reason", "交叉引用"),
            "status": status,
        })
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
        text = file_path.read_text(encoding='utf-8')
        meta, _ = parse_frontmatter(text)
        if not meta:
            return ""
        topic = meta.get('topic')
        if isinstance(topic, list):
            return str(topic[0]).strip() if len(topic) == 1 else ""
        if isinstance(topic, str) and topic.strip():
            return topic.strip()
    except Exception as e:
        sys.stderr.write(f"[_read_file_topic] read failed: {e}\n"); sys.stderr.flush()
    return ""


def _iter_md_files(workspace: Path) -> List[Path]:
    """收集所有 MD 文件（排除隐藏文件和忽略目录）"""
    excluded = {'AI Wiki', '.git', '.obsidian', '.trash', 'wiki'}
    files = []
    for folder in workspace.iterdir():
        if not folder.is_dir():
            continue
        if folder.name in excluded or folder.name.startswith('.'):
            continue
        if is_ignored_dir(folder.name):
            continue
        for md_file in folder.rglob('*.md'):
            if md_file.name.startswith('.'):
                continue
            files.append(md_file)
    return files


def _parse_file_meta(md_file: Path) -> Dict[str, Any]:
    try:
        text = md_file.read_text(encoding='utf-8')
    except Exception as e:
        logger.warning(f"[link_indexer] 无法读取文件 {md_file.name}: {e}")
        return None

    meta, body = parse_frontmatter(text)
    title = md_file.stem
    tags = []
    topic = None

    if meta:
        t = meta.get('title')
        if t and isinstance(t, str):
            title = t
        raw_tags = meta.get('tags', [])
        if isinstance(raw_tags, list):
            tags = [str(t).strip() for t in raw_tags if t]
        elif isinstance(raw_tags, str) and raw_tags.strip():
            tags = [raw_tags.strip()]
        raw_topic = meta.get('topic')
        if isinstance(raw_topic, str) and raw_topic.strip():
            topic = raw_topic.strip()
    else:
        body = text

    summary = body[:500].replace('\n', ' ').strip()
    rel_path = str(md_file.relative_to(Path(config.workspace_path)))

    return {
        "path": rel_path,
        "title": title,
        "tags": tags,
        "topic": topic,
        "summary": summary,
    }


def _build_candidate_pairs(metas: List[Dict]) -> List[Tuple[Dict, Dict, int]]:
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
                a_tokens = set(_normalize_for_match(t) for t in tokenize_text(a["title"])
                              if _is_meaningful_tag(t) and not _is_generic_word(t))
                b_tokens = set(_normalize_for_match(t) for t in tokenize_text(b["title"])
                              if _is_meaningful_tag(t) and not _is_generic_word(t))
                if len(a_tokens & b_tokens) >= 2:
                    priority = 3

            if priority > 0:
                pairs.append((a, b, priority))
                seen.add(pair_key)

    # 按优先级排序，限制最多 200 对走 AI
    pairs.sort(key=lambda x: x[2])
    return pairs[:200]


def _ask_llm_for_links(candidate_pairs: List[Tuple[Dict, Dict, int]],
                        progress_callback=None) -> List[Dict]:
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
    batch_size = 15

    total_batches = (len(candidate_pairs) + batch_size - 1) // batch_size

    for batch_idx in range(0, len(candidate_pairs), batch_size):
        batch = candidate_pairs[batch_idx:batch_idx + batch_size]

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

        prompt = f"""以下是为每对文章编号的列表。请判断每对文章之间是否存在内容重叠或相似之处。

判断标准：
- 两篇文章讨论相同的主题、技术、工具或概念
- 一篇文章的内容是另一篇的补充、延伸或前置知识
- 两篇文章有实质性的交叉引用价值

请返回 JSON 数组，仅包含有关联的对：
[{{"pair": [1, 2], "reason": "简述关联原因（10字以内）"}}, ...]

如果某对没有关联，不要包含在结果中。只返回 JSON 数组，不要其他文字。

{chr(10).join(lines)}"""

        try:
            response = call_llm_raw(prompt, temperature=0.3)
            # 提取 JSON
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                results = json.loads(json_match.group(0))
                for item in results:
                    pair = item.get("pair", [])
                    reason = item.get("reason", "")
                    if len(pair) == 2:
                        local_idx = pair[0]
                        if local_idx in idx_map:
                            meta_a, meta_b = idx_map[local_idx]
                            all_links.append({
                                "from": meta_a["path"],
                                "to": meta_b["path"],
                                "reason": reason,
                                "status": "pending",
                            })
        except Exception as e:
            logger.warning(f"[link_indexer] LLM batch error: {e}")
            continue

        if progress_callback:
            current_batch = batch_idx // batch_size + 1
            progress_callback(current_batch, total_batches,
                            f"AI 分析中 ({current_batch}/{total_batches})")

    return all_links


def discover_links(progress_callback=None) -> Dict[str, Any]:
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

    # Step 1: 提取元数据
    if progress_callback:
        progress_callback(0, 3, "正在读取文件元数据...")

    metas = []
    for f in md_files:
        meta = _parse_file_meta(f)
        if meta:
            metas.append(meta)

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

    existing_keys = set()
    for l in existing_links:
        key = tuple(sorted([l["from"], l["to"]]))
        existing_keys.add(key)

    merged = list(existing_links)
    added_count = 0
    for link in new_links:
        key = tuple(sorted([link["from"], link["to"]]))
        if key not in existing_keys:
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


def get_backlinks(file_path: str) -> Dict[str, Any]:
    """获取指定文件的链接；file_path 为空时返回所有链接"""
    data = load_links()
    all_links = data.get("links", [])

    if not file_path:
        links = []
        for link in all_links:
            links.append({
                "from": link["from"],
                "to": link["to"],
                "file": link["from"],
                "other": link["to"],
                "reason": link.get("reason", ""),
                "status": link.get("status", "pending"),
                "direction": "outgoing",
            })
        return {
            "success": True,
            "file": "",
            "links": links,
            "count": len(links),
        }

    incoming = []
    for link in all_links:
        if link["to"] == file_path or link["from"] == file_path:
            other = link["from"] if link["to"] == file_path else link["to"]
            incoming.append({
                "from": link["from"],
                "to": link["to"],
                "file": other,
                "reason": link.get("reason", ""),
                "status": link.get("status", "pending"),
                "direction": "incoming" if link["to"] == file_path else "outgoing",
            })

    return {
        "success": True,
        "file": file_path,
        "links": incoming,
        "count": len(incoming),
    }


def confirm_link(from_path: str, to_path: str) -> Dict[str, Any]:
    """确认一个链接"""
    data = load_links()
    links = data.get("links", [])
    found = False
    for link in links:
        key1 = (link["from"] == from_path and link["to"] == to_path)
        key2 = (link["from"] == to_path and link["to"] == from_path)
        if key1 or key2:
            link["status"] = "confirmed"
            found = True
            break
    if found:
        save_links(data)
        return {"success": True, "message": "链接已确认"}
    return {"success": False, "message": "链接不存在"}


def reject_link(from_path: str, to_path: str) -> Dict[str, Any]:
    """删除一个链接"""
    data = load_links()
    links = data.get("links", [])
    new_links = []
    removed = False
    for link in links:
        key1 = (link["from"] == from_path and link["to"] == to_path)
        key2 = (link["from"] == to_path and link["to"] == from_path)
        if key1 or key2:
            removed = True
            continue
        new_links.append(link)
    if removed:
        data["links"] = new_links
        save_links(data)
        return {"success": True, "message": "链接已删除"}
    return {"success": False, "message": "链接不存在"}


def confirm_all_links() -> Dict[str, Any]:
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
