"""
双向链接索引引擎

两阶段发现：
1. 本地粗筛：同 topic / 共享 tag / 文件名 token 重叠 → 候选对
2. AI 精判：批处理候选对，LLM 判断是否内容相关

存储：workspace/.links.json
"""

import json
import re
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from config import config, is_ignored_dir
from utils.text_utils import tokenize as tokenize_text, _is_meaningful_tag, _is_generic_word, _normalize_for_match


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
    except Exception:
        return {"links": [], "last_scan": None}


def save_links(data: Dict[str, Any]) -> bool:
    path = _get_links_path()
    if not path:
        return False
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        return True
    except Exception:
        return False


def _iter_md_files(workspace: Path) -> List[Path]:
    """收集所有 MD 文件（排除隐藏文件和忽略目录）"""
    excluded = {'AI Wiki', '.git', '.obsidian', '.trash'}
    files = []
    for folder in workspace.iterdir():
        if not folder.is_dir():
            continue
        if folder.name in excluded or folder.name.startswith('.'):
            continue
        if is_ignored_dir(folder.name):
            continue
        for md_file in folder.rglob('*.md'):
            if md_file.name.startswith('.') or md_file.name.lower() in ('wiki.md', 'tags.md'):
                continue
            files.append(md_file)
    return files


def _parse_file_meta(md_file: Path) -> Dict[str, Any]:
    """提取文件的标题、标签、topic、前 500 字摘要"""
    try:
        text = md_file.read_text(encoding='utf-8')
    except Exception:
        return None

    m = re.match(r'^\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---', text.lstrip('﻿'))
    title = md_file.stem
    tags = []
    topic = None

    if m:
        yaml_text = m.group(1)
        body = text[m.end():].strip() if not text.startswith('﻿') else text[m.end() + 1:].strip()
        for line in yaml_text.split('\n'):
            idx = line.find(':')
            if idx < 0:
                continue
            key = line[:idx].strip()
            val = line[idx + 1:].strip()
            if key == 'title':
                title = val.strip().strip("'\"")
            elif key == 'tags' and val.startswith('[') and val.endswith(']'):
                tags = [t.strip().strip("'\"") for t in val[1:-1].split(',') if t.strip()]
            elif key == 'topic':
                topic = val.strip().strip("'\"")
    else:
        body = text.strip()

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
        import sys
        sys.stderr.write(f"[link_indexer] API not configured: {msg}\n")
        sys.stderr.flush()
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
            import sys
            sys.stderr.write(f"[link_indexer] LLM batch error: {e}\n")
            sys.stderr.flush()
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

    # Step 4: 合并到已有链接
    existing = load_links()
    existing_links = existing.get("links", [])

    # 保留已确认的链接
    confirmed = [l for l in existing_links if l.get("status") == "confirmed"]

    # 生成已存在链接的 key set（用于去重）
    existing_keys = set()
    for l in existing_links:
        key = tuple(sorted([l["from"], l["to"]]))
        existing_keys.add(key)

    # 合并新链接（去重）
    merged = list(existing_links)
    added_count = 0
    for link in new_links:
        key = tuple(sorted([link["from"], link["to"]]))
        if key not in existing_keys:
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
