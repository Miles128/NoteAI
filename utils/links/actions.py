"""Confirm / reject / list backlinks against .links.json."""

from __future__ import annotations

from typing import Any

from utils.links.persist import (
    _dedupe_links,
    _is_self_link,
    _normalize_link_path,
    load_links,
    save_links,
)


def get_backlinks(file_path: str) -> dict[str, Any]:
    """获取指定文件的链接；file_path 为空时返回所有链接。"""
    data = load_links()
    all_links = _dedupe_links(data.get("links", []))
    norm_center = _normalize_link_path(file_path)

    def _to_view(link: dict[str, Any]) -> dict[str, Any]:
        # 归一化比较，避免 ``./Notes/A.md`` 与 ``Notes/A.md`` 等写法差异导致方向判错
        is_incoming = norm_center and _normalize_link_path(link["to"]) == norm_center
        other = link["from"] if is_incoming else link["to"]
        return {
            "from": link["from"],
            "to": link["to"],
            "file": other,
            "other": other,
            "reason": link.get("reason", ""),
            "status": link.get("status", "confirmed"),
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

    related = [
        _to_view(link)
        for link in all_links
        if _normalize_link_path(link["to"]) == norm_center or _normalize_link_path(link["from"]) == norm_center
    ]

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
