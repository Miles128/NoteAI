"""Multi-source ingest: RSS feeds, transcripts → Notes Markdown."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from config import config
from config.settings import NOTES_FOLDER
from utils.helpers import sanitize_filename

_INBOX = "_采集"


def _inbox_dir(workspace: str) -> Path:
    p = Path(workspace) / NOTES_FOLDER / _INBOX
    p.mkdir(parents=True, exist_ok=True)
    return p


def _unique_md_path(folder: Path, stem: str) -> Path:
    base = sanitize_filename(stem) or "未命名"
    candidate = folder / f"{base}.md"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = folder / f"{base}_{n}.md"
        if not candidate.exists():
            return candidate
        n += 1


def _write_note(
    title: str,
    body: str,
    *,
    source_type: str,
    source_url: str = "",
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = config.workspace_path
    if not workspace:
        return {"success": False, "message": "未设置工作区"}

    folder = _inbox_dir(workspace)
    path = _unique_md_path(folder, title)
    meta_lines = [
        "---",
        f'title: "{title.replace(chr(34), "")}"',
        f"source_type: {source_type}",
        f"imported_at: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
    ]
    if source_url:
        meta_lines.append(f'source_url: "{source_url}"')
    if extra_meta:
        for k, v in extra_meta.items():
            if v is not None and v != "":
                meta_lines.append(f"{k}: {v}")
    meta_lines.append("---")
    content = "\n".join(meta_lines) + "\n\n" + body.strip() + "\n"
    path.write_text(content, encoding="utf-8")
    rel = str(path.relative_to(Path(workspace)))
    return {"success": True, "path": rel, "title": title, "message": f"已保存 {rel}"}


def _fetch_rss(url: str, timeout: int = 20) -> ET.Element:
    resp = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "NoteAI/1.0 RSS Reader"},
    )
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _rss_items(root: ET.Element) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or item.findtext("summary") or "").strip()
        if title or link:
            items.append({"title": title or link, "link": link, "description": desc})
    if items:
        return items
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
        link_el = entry.find("a:link", ns)
        link = (link_el.get("href") if link_el is not None else "") or ""
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        content = (entry.findtext("a:content", default="", namespaces=ns) or "").strip()
        body = summary or content
        if title or link:
            items.append({"title": title or link, "link": link, "description": body})
    return items


def import_rss_feed(feed_url: str, *, max_items: int = 10, fetch_articles: bool = True) -> dict[str, Any]:
    """Fetch RSS/Atom entries; optionally download linked articles as Markdown."""
    feed_url = (feed_url or "").strip()
    if not feed_url:
        return {"success": False, "message": "RSS URL 为空"}

    try:
        root = _fetch_rss(feed_url)
    except Exception as e:
        return {"success": False, "message": f"RSS 获取失败: {e}"}

    entries = _rss_items(root)[: max(1, min(max_items, 30))]
    if not entries:
        return {"success": False, "message": "RSS 中无条目"}

    saved: list[str] = []
    errors: list[str] = []

    if fetch_articles:
        from modules.web_downloader import WebDownloader

        downloader = WebDownloader(include_images=False)
        workspace = config.workspace_path or ""
        urls = [e.get("link", "") for e in entries if e.get("link", "").startswith("http")]
        if urls:
            batch = downloader.download_batch(urls, workspace)
            for item in batch:
                if item.get("success") and item.get("file_path"):
                    try:
                        saved.append(str(Path(item["file_path"]).relative_to(Path(workspace))))
                    except ValueError:
                        saved.append(item["file_path"])
                elif item.get("url"):
                    errors.append(item["url"])
    else:
        for entry in entries:
            title = entry.get("title") or "RSS 条目"
            desc = re.sub(r"<[^>]+>", "", entry.get("description", ""))
            link = entry.get("link", "")
            body = desc or f"来源：{link}"
            if link:
                body += f"\n\n[原文]({link})"
            r = _write_note(title, body, source_type="rss", source_url=link or feed_url)
            if r.get("success"):
                saved.append(r["path"])

    return {
        "success": bool(saved),
        "imported": len(saved),
        "paths": saved,
        "errors": errors,
        "message": f"RSS 导入 {len(saved)} 篇" + (f"，失败 {len(errors)}" if errors else ""),
    }


def import_transcript(
    title: str,
    content: str,
    *,
    source: str = "",
    speakers: str = "",
) -> dict[str, Any]:
    title = (title or "").strip() or "转录"
    content = (content or "").strip()
    if not content:
        return {"success": False, "message": "转录内容为空"}
    extra: dict[str, Any] = {}
    if source:
        extra["transcript_source"] = source
    if speakers:
        extra["speakers"] = speakers
    body = content
    if speakers:
        body = f"**说话人**: {speakers}\n\n{body}"
    return _write_note(title, body, source_type="transcript", extra_meta=extra)


# ── RSS Subscription Persistence ──

import json

_SUBS_FILE = "rss_subscriptions.json"


def _subs_path(workspace: str) -> Path:
    return Path(workspace) / ".noteai" / _SUBS_FILE


def load_subscriptions(workspace: str) -> list[dict]:
    p = _subs_path(workspace)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_subscription(workspace: str, url: str, name: str = "") -> None:
    subs = load_subscriptions(workspace)
    if any(s["url"] == url for s in subs):
        return
    subs.append({"url": url, "name": name or url, "last_fetched": None, "interval_minutes": 30})
    _subs_path(workspace).parent.mkdir(parents=True, exist_ok=True)
    _subs_path(workspace).write_text(json.dumps(subs, ensure_ascii=False, indent=2), encoding="utf-8")


def remove_subscription(workspace: str, url: str) -> None:
    subs = load_subscriptions(workspace)
    subs = [s for s in subs if s["url"] != url]
    _subs_path(workspace).write_text(json.dumps(subs, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_all_subscriptions(workspace: str) -> dict:
    subs = load_subscriptions(workspace)
    results = []
    for sub in subs:
        try:
            r = import_rss_feed(sub["url"], max_items=10, fetch_articles=True)
            results.append({"url": sub["url"], "success": r.get("success", False), "imported": r.get("imported", 0)})
            if r.get("success"):
                sub["last_fetched"] = datetime.now(timezone.utc).isoformat()
        except Exception as e:
            results.append({"url": sub["url"], "success": False, "error": str(e)})
    if subs:
        _subs_path(workspace).write_text(json.dumps(subs, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"success": True, "results": results}
