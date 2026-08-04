"""Multi-source ingest: RSS feeds, transcripts → Notes Markdown."""

from __future__ import annotations

import json
import re
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from config import config
from config.settings import NOTES_FOLDER
from utils.helpers import is_valid_url, sanitize_filename
from utils.logger import logger
from utils.network_security import safe_get

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
    resp = safe_get(
        requests,
        url,
        timeout=timeout,
        headers={"User-Agent": "NoteAI/1.0 RSS Reader"},
    )
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _rss_title(root: ET.Element) -> str:
    """Extract the feed title from RSS 2.0 / Atom feeds."""
    channel = root.find("channel")
    if channel is not None:
        t = (channel.findtext("title") or "").strip()
        if t:
            return t
    ns = {"a": "http://www.w3.org/2005/Atom"}
    return (root.findtext("a:title", default="", namespaces=ns) or "").strip()


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


def _persist_subscriptions(workspace: str, subs: list[dict]) -> None:
    _subs_path(workspace).parent.mkdir(parents=True, exist_ok=True)
    _subs_path(workspace).write_text(json.dumps(subs, ensure_ascii=False, indent=2), encoding="utf-8")


def save_subscription(workspace: str, url: str, name: str = "") -> dict:
    """保存订阅：校验 URL，未提供名称时尝试从 feed 获取标题。"""
    url = (url or "").strip()
    if not url or not is_valid_url(url):
        return {"success": False, "message": "无效的 RSS URL"}

    subs = load_subscriptions(workspace)
    for sub in subs:
        if sub["url"] == url:
            if name and sub.get("name") != name:
                sub["name"] = name
                _persist_subscriptions(workspace, subs)
            return {"success": True, "message": "订阅已存在"}

    feed_name = name.strip()
    if not feed_name:
        try:
            root = _fetch_rss(url)
            feed_name = _rss_title(root)
        except Exception:
            feed_name = ""

    subs.append(
        {
            "url": url,
            "name": feed_name or url,
            "last_fetched": None,
            "interval_minutes": 30,
        }
    )
    _persist_subscriptions(workspace, subs)
    return {"success": True, "message": "订阅已保存"}


def remove_subscription(workspace: str, url: str) -> dict:
    url = (url or "").strip()
    subs = load_subscriptions(workspace)
    kept = [s for s in subs if s["url"] != url]
    if len(kept) == len(subs):
        return {"success": False, "message": "未找到该订阅"}
    _persist_subscriptions(workspace, kept)
    return {"success": True, "message": "订阅已移除"}


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
        _persist_subscriptions(workspace, subs)
    return {"success": True, "results": results}


# ── RSS Automatic Polling ──


class RssScheduler:
    """后台定时轮询 RSS 订阅，到期订阅自动拉取并把新内容导入知识库。

    每个订阅按 ``interval_minutes``（默认 30 分钟）触发一次；首次添加且从未
    拉取过的订阅会在第一个 tick 后自动拉取。

    Args:
        workspace_provider: 返回当前工作区路径（切换工作区后自动生效）。
        send_event: 拉取完成后的事件回调（发送 rss_poll_complete 事件）。
        tick_seconds: 调度检查间隔。
    """

    def __init__(
        self,
        workspace_provider: Any,
        send_event: Any = None,
        tick_seconds: int = 60,
    ):
        self._workspace_provider = workspace_provider
        self._send_event = send_event
        self._tick_seconds = max(30, int(tick_seconds))
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._inflight: set[str] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rss-scheduler", daemon=True)
        self._thread.start()
        logger.info("[rss-scheduler] 已启动，轮询间隔 %ss", self._tick_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("[rss-scheduler] 已停止")

    def _run(self) -> None:
        while not self._stop.wait(self._tick_seconds):
            try:
                self._poll_due_subscriptions()
            except Exception as e:
                logger.warning(f"[rss-scheduler] tick 失败: {e}")

    def _poll_due_subscriptions(self) -> None:
        workspace = self._workspace_provider()
        if not workspace or not Path(workspace).exists():
            return
        for sub in load_subscriptions(workspace):
            url = sub.get("url", "")
            if not url or not self._is_due(sub) or url in self._inflight:
                continue
            self._inflight.add(url)
            threading.Thread(
                target=self._fetch_one,
                args=(workspace, url),
                daemon=True,
            ).start()

    @staticmethod
    def _is_due(sub: dict) -> bool:
        """判断订阅是否到期：无 last_fetched 或距上次拉取超过 interval_minutes。"""
        interval_minutes = float(sub.get("interval_minutes") or 30)
        last = sub.get("last_fetched")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(str(last))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
            return elapsed >= interval_minutes * 60
        except Exception:
            return True

    def _fetch_one(self, workspace: str, url: str) -> None:
        try:
            result = import_rss_feed(url, max_items=10, fetch_articles=True)
            self._mark_fetched(workspace, url)
            imported = int(result.get("imported") or 0)
            logger.info(f"[rss-scheduler] {url} 拉取完成: {imported} 篇")
            if self._send_event:
                self._send_event(
                    {
                        "type": "rss_poll_complete",
                        "data": {"url": url, "imported": imported},
                    }
                )
        except Exception as e:
            logger.warning(f"[rss-scheduler] {url} 拉取失败: {e}")
        finally:
            self._inflight.discard(url)

    def _mark_fetched(self, workspace: str, url: str) -> None:
        try:
            subs = load_subscriptions(workspace)
            for sub in subs:
                if sub.get("url") == url:
                    sub["last_fetched"] = datetime.now(timezone.utc).isoformat()
                    break
            _persist_subscriptions(workspace, subs)
        except Exception as e:
            logger.warning(f"[rss-scheduler] 更新 last_fetched 失败: {e}")
