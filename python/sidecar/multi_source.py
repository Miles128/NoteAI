"""Multi-source ingest: RSS feeds → Notes Markdown；RSS 源推荐。"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from config import config
from config.settings import NOTES_FOLDER
from prompts import RSS_DISCOVERY_PROMPT
from utils.helpers import is_valid_url, sanitize_filename
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


# ── RSS 源推荐（内置目录 + LLM 主题匹配） ──

# 内置 AI 主题候选源（name | url | topics 标签）
_BUILTIN_FEEDS: list[dict] = [
    {"name": "OpenAI Blog", "url": "https://openai.com/blog/rss.xml", "topics": ["llm", "model", "industry"]},
    {"name": "Anthropic News", "url": "https://www.anthropic.com/rss.xml", "topics": ["llm", "agent", "industry"]},
    {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "topics": ["llm", "open-source", "ml"],
    },
    {"name": "arXiv cs.AI", "url": "https://rss.arxiv.org/rss/cs.AI", "topics": ["paper", "research", "ml"]},
    {"name": "arXiv cs.CL", "url": "https://rss.arxiv.org/rss/cs.CL", "topics": ["paper", "nlp", "llm"]},
    {"name": "arXiv cs.LG", "url": "https://rss.arxiv.org/rss/cs.LG", "topics": ["paper", "ml", "research"]},
    {"name": "Google DeepMind", "url": "https://deepmind.google/blog/rss.xml", "topics": ["research", "ml", "agent"]},
    {
        "name": "Google AI Blog",
        "url": "https://blog.google/technology/ai/rss/",
        "topics": ["llm", "product", "research"],
    },
    {
        "name": "Lilian Weng (Lil'Log)",
        "url": "https://lilianweng.github.io/posts.rss",
        "topics": ["llm", "agent", "tutorial"],
    },
    {
        "name": "Simon Willison's Weblog",
        "url": "https://simonwillison.net/atom/everything/",
        "topics": ["llm", "tools", "industry"],
    },
    {"name": "The Gradient", "url": "https://thegradient.pub/feed/", "topics": ["research", "llm", "analysis"]},
    {"name": "BAIR Blog", "url": "https://bair.berkeley.edu/blog/feed.xml", "topics": ["research", "ml", "paper"]},
    {
        "name": "MIT Tech Review AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        "topics": ["industry", "product", "analysis"],
    },
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "topics": ["industry", "llm", "news"]},
    {"name": "量子位", "url": "https://www.qbitai.com/feed", "topics": ["industry", "llm", "news"]},
    {"name": "InfoQ 中文", "url": "https://www.infoq.cn/feed", "topics": ["industry", "engineering", "news"]},
    {"name": "少数派", "url": "https://sspai.com/feed", "topics": ["product", "tools", "tutorial"]},
    {"name": "MarkTechPost", "url": "https://www.marktechpost.com/feed/", "topics": ["llm", "research", "news"]},
]


def load_knowledge_topics(workspace: str) -> list[str]:
    """从 Notes 目录收集主题名（作为匹配信号）。"""
    notes = Path(workspace) / "Notes"
    if not notes.exists():
        return []
    topics = []
    for child in sorted(notes.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            topics.append(child.name)
    return topics


def _parse_builtin_urls(raw: str) -> list[str]:
    """解析 LLM 输出：{"builtin_urls": [...]}"""
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 容错：找 JSON 对象
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            return []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
    return [str(u).strip() for u in (data.get("builtin_urls") or []) if str(u).strip()]


def discover_rss_sources(workspace: str, llm_call=None) -> dict[str, Any]:
    """从内置 RSS 目录中推荐与知识库主题匹配的源。

    ``llm_call(prompt) -> str`` 可注入；默认 call_llm_raw。
    只读分析：不写入订阅，由调用方（transfer_handler）负责 save_subscription。
    """
    if llm_call is None:
        from utils.llm_utils import call_llm_raw

        def llm_call(prompt: str) -> str:
            return call_llm_raw(prompt, temperature=0.2)

    topics = load_knowledge_topics(workspace)
    if not topics:
        return {"success": False, "message": "未找到知识库主题", "recommendations": []}

    builtin_lines = "\n".join(f"- {f['name']} | {f['url']} | {','.join(f['topics'])}" for f in _BUILTIN_FEEDS)
    prompt = RSS_DISCOVERY_PROMPT.format(topics="、".join(topics), builtin_feeds=builtin_lines)
    try:
        raw = llm_call(prompt)
    except Exception as exc:
        return {"success": False, "message": f"推荐规划失败: {exc}", "recommendations": []}
    builtin_urls = _parse_builtin_urls(raw)

    subscribed = {s["url"] for s in load_subscriptions(workspace)}
    recommendations: list[dict] = []
    seen: set[str] = set()
    for feed in _BUILTIN_FEEDS:
        if feed["url"] in builtin_urls and feed["url"] not in seen:
            seen.add(feed["url"])
            recommendations.append(
                {
                    "name": feed["name"],
                    "url": feed["url"],
                    "topics": feed["topics"],
                    "source": "builtin",
                    "subscribed": feed["url"] in subscribed,
                }
            )

    return {
        "success": True,
        "topics": topics,
        "recommendations": recommendations,
        "message": f"发现 {len(recommendations)} 个推荐源",
    }
