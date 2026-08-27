"""workspace/.links.json persistence, path keys, weak-heuristic purge."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from config import config
from utils.logger import logger


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


def _normalize_link_path(path: str) -> str:
    """归一化链接路径：去空白、折叠 . / .. 段，再按大小写不敏感比较。"""
    return os.path.normpath(str(path or "")).strip().casefold()


def _is_self_link(from_path: str, to_path: str) -> bool:
    """自引用检查：同一文件的链接不存储。

    路径先归一化（去除 ``./`` 前缀、``.``/``..`` 段、空白），再按大小写不敏感
    比较，避免 ``Notes/A.md`` 与 ``./notes/a.md`` 这类写法不同的自引用漏判。
    """
    return _normalize_link_path(from_path) == _normalize_link_path(to_path)


def _is_readme_note(path: str | Path) -> bool:
    """README 是目录说明，不参与笔记链接图。"""
    return Path(str(path)).stem.casefold() == "readme"


def _normalize_links(links: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Drop README links; keep each record's own status (pending stays pending)."""
    normalized: list[dict[str, Any]] = []
    changed = 0
    for link in links:
        from_path = link.get("from", "")
        to_path = link.get("to", "")
        if _is_readme_note(from_path) or _is_readme_note(to_path):
            changed += 1
            continue
        normalized.append(link)
    return normalized, changed


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
    normalized, normalized_changes = _normalize_links(deduped)
    dedupe_changes = len(links) - len(deduped)
    if dedupe_changes or normalized_changes:
        logger.info(
            f"[link_indexer] 归一链接索引: 去重/自引用 {dedupe_changes} 条，自动确认/忽略 README {normalized_changes} 条"
        )
        data["links"] = normalized
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
    changed = 0
    for link in links:
        from_path = link.get("from", "")
        to_path = link.get("to", "")
        if _is_self_link(from_path, to_path):
            logger.info(f"[link_indexer] 清理自引用链接: {from_path} -> {to_path}")
            continue
        if _is_readme_note(from_path) or _is_readme_note(to_path):
            logger.info(f"[link_indexer] 清理 README 链接: {from_path} -> {to_path}")
            continue
        from_full = ws / from_path if not Path(from_path).is_absolute() else Path(from_path)
        to_full = ws / to_path if not Path(to_path).is_absolute() else Path(to_path)
        if not from_full.exists() or not to_full.exists():
            logger.info(f"[link_indexer] 清理无效链接: {from_path} -> {to_path}")
            continue
        if not link.get("status"):
            link["status"] = "pending"
            changed += 1
        valid.append(link)
    changed += original_count - len(valid)
    if changed > 0:
        data["links"] = valid
        save_links(data)
    return changed


#: 弱启发式原因：标签/语义/邻居产生的高对称链接，不视为真实引用
_WEAK_LINK_REASONS = ("共享标签", "语义相关", "已确认链接的邻居", "同主题")


def _is_weak_heuristic_link(reason: str) -> bool:
    """启发式对称信号（标签/向量/邻居/同主题）产生的链接是否属于弱链接。"""
    return any(reason.startswith(prefix) for prefix in _WEAK_LINK_REASONS)


def purge_weak_links() -> dict[str, Any]:
    """
    清洗 .links.json：删除由弱启发式（共享标签 / 语义相关 / 邻居 / 同主题）
    产生的低置信链接，只保留真实引用（正文/摘要提及）与实体/概念共享。

    返回统计信息；保留最新 last_scan，避免触发重复扫描。
    """
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区", "removed": 0}
    data = load_links()
    links = data.get("links", [])
    original_count = len(links)
    kept: list[dict[str, Any]] = []
    removed = 0
    for link in links:
        reason = str(link.get("reason") or "").strip()
        if _is_weak_heuristic_link(reason):
            removed += 1
            continue
        kept.append(link)
    if removed:
        save_links({"links": kept, "last_scan": data.get("last_scan")})
        logger.info(f"[link_indexer] 弱启发式清洗: 删除 {removed} 条，保留 {len(kept)} 条")
    return {
        "success": True,
        "total": original_count,
        "removed": removed,
        "kept": len(kept),
    }
