"""RSS 源自动发现：内置候选目录（A）+ 联网搜索发现（B）。

- A：内置知名 AI/技术 RSS 目录（带主题标签），由 LLM 按知识库主题匹配推荐；
- B：LLM 根据知识库主题生成搜索词，经 rag/web_search 的 DuckDuckGo/Bing
  搜索发现新源，抓取页面提取 feed 链接并验证可用性；
- 两路候选合并去重，输出推荐列表（标注来源 builtin/search、是否已订阅）。

只读分析：不写入订阅，由调用方（transfer_handler）负责 save_subscription。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from prompts import DEEPSEEK_WEB_DISCOVERY_PROMPT, RSS_DISCOVERY_PROMPT
from sidecar.multi_source import _fetch_rss, _rss_title, load_subscriptions

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

# feed 链接特征：从搜索结果 URL 或网页中识别 RSS 地址
_FEED_PATH_RE = re.compile(r"(?:rss|feed|atom|feedburner|/feed/?$|/rss/?$|/atom/?$)", re.IGNORECASE)

_MAX_SEARCH_QUERIES = 6
_MAX_SEARCH_RESULTS = 20
_MAX_VALIDATE = 12
_MAX_TOTAL_CANDIDATES = 25


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


def _parse_llm_plan(raw: str) -> tuple[list[str], list[str]]:
    """解析 LLM 输出：{"queries": [...], "builtin_urls": [...]}"""
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
            return [], []
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return [], []
    queries = [str(q).strip() for q in (data.get("queries") or []) if str(q).strip()]
    urls = [str(u).strip() for u in (data.get("builtin_urls") or []) if str(u).strip()]
    return queries[:_MAX_SEARCH_QUERIES], urls


def _search_web(query: str) -> list[dict]:
    """联网搜索并返回候选（url/title），失败返回空。"""
    try:
        from sidecar.rag.web_search import web_search

        results = web_search(query)
    except Exception:
        return []
    candidates = []
    for item in results or []:
        url = str(item.get("url") or item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not url.startswith("http"):
            continue
        candidates.append({"url": url, "title": title})
    return candidates[:_MAX_SEARCH_RESULTS]


def _find_feed_url(candidate: dict) -> str:
    """从搜索结果条目推断 feed URL：URL 本身像 feed 直接用；
    否则抓取页面找 <link rel=alternate type=rss> 或页面内 feed 链接。"""
    url = candidate["url"]
    if _FEED_PATH_RE.search(url):
        return url
    try:
        from sidecar.rag.web_search import fetch_page_content

        html = fetch_page_content(url)
    except Exception:
        return ""
    if not html:
        return ""
    # <link rel="alternate" type="application/rss+xml" href="...">
    link_re = re.compile(
        r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+href=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    for match in link_re.finditer(html):
        href = match.group(1)
        if href.startswith("/"):
            from urllib.parse import urlsplit, urlunsplit

            parts = urlsplit(url)
            href = urlunsplit((parts.scheme, parts.netloc, href, "", ""))
        if href.startswith("http"):
            return href
    return ""


# 常见 feed 路径变体：搜索结果多为文章/导航页，直接探测站点的标准 feed 地址
_COMMON_FEED_PATHS = ("/feed/", "/feed", "/rss.xml", "/rss/", "/atom.xml", "/index.xml", "/blog/feed.xml", "/feed.xml")


def _guess_feed_from_domain(domain: str, max_probe: int = 4) -> str:
    """对站点域名探测常见 feed 路径，返回第一个可解析的 feed URL。"""
    for path in _COMMON_FEED_PATHS[:max_probe]:
        url = f"https://{domain}{path}"
        if _validate_feed(url):
            return url
    return ""


def _validate_feed(url: str) -> str | None:
    """验证 feed 可解析，返回标题；失败返回 None。"""
    try:
        root = _fetch_rss(url)
        return _rss_title(root) or url
    except Exception:
        return None


def _deepseek_web_discovery(topics: list[str]) -> list[dict]:
    """DeepSeek response API 内置 web_search 工具：模型自主搜索并直接给出
    feed 地址，比 DDG 搜索+域名探测更精准。仅当 api_base 为 deepseek.com
    时启用；失败/不可用时返回空（调用方降级到 DDG 路径）。"""
    from config import config

    if "deepseek.com" not in (config.api_base or ""):
        return []
    import json as _json

    import requests as _requests

    payload = {
        "model": config.model_name,
        "input": DEEPSEEK_WEB_DISCOVERY_PROMPT.format(topics="、".join(topics)),
        "tools": [{"type": "web_search"}],
        "max_output_tokens": 2048,
    }
    try:
        resp = _requests.post(
            f"{config.api_base.rstrip('/')}/responses",
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
        if resp.status_code != 200:
            return []
        body = resp.json()
    except Exception:
        return []

    text_parts: list[str] = []
    for item in body.get("output") or []:
        if item.get("type") == "message":
            for content in item.get("content") or []:
                text_parts.append(str(content.get("text") or ""))
    text = "\n".join(text_parts)

    feeds: list[dict] = []
    seen: set[str] = set()
    # 1) 模型按 JSON 输出（name/url 对）
    json_block = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    raw_json = json_block.group(1) if json_block else ""
    if not raw_json:
        start, end = text.find("{"), text.rfind("}")
        raw_json = text[start : end + 1] if 0 <= start < end else ""
    if raw_json:
        try:
            data = _json.loads(raw_json)
            for item in data.get("feeds") or data.get("sources") or []:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or item.get("feed") or "").strip()
                name = str(item.get("name") or "").strip()
                if url.startswith("http") and url not in seen:
                    seen.add(url)
                    feeds.append({"url": url, "name": name})
        except Exception:
            pass
    # 2) 兜底：抓取文本中所有 http URL，逐个验证
    if not feeds:
        for url in re.findall(r"https?://[^\s<>\"']+", text):
            url = url.rstrip(".,;)]}")
            if url in seen:
                continue
            seen.add(url)
            feeds.append({"url": url, "name": ""})
    return feeds


def discover_rss_sources(workspace: str, llm_call=None) -> dict[str, Any]:
    """自动发现并推荐 RSS 源（内置目录匹配 + 联网搜索发现）。

    ``llm_call(prompt) -> str`` 可注入；默认 call_llm_raw。
    返回推荐列表（builtin/search 混合，标注是否已订阅）。
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
    queries, builtin_urls = _parse_llm_plan(raw)

    # ── A 路：内置目录推荐（LLM 已选 url） ──
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

    # ── B 路：联网搜索发现新源 ──
    # 优先 DeepSeek response API 内置 web_search（模型自主搜索直接给 feed）；
    # 不可用时降级 DDG 搜索 + 站点域名 feed 路径探测。
    discovered: dict[str, str] = {}  # url -> title
    deepseek_feeds = _deepseek_web_discovery(topics)
    for feed in deepseek_feeds:
        url, name = feed["url"], feed["name"]
        if url in seen or url in discovered:
            continue
        feed_title = _validate_feed(url)
        if feed_title is None:
            continue
        discovered[url] = name or feed_title

    if not discovered:
        pending_domains: dict[str, str] = {}  # domain -> title
        for query in queries:
            candidates = _search_web(query)
            for candidate in candidates:
                url = candidate["url"]
                if url in seen or url in discovered:
                    continue
                if _FEED_PATH_RE.search(url):
                    discovered[url] = candidate.get("title", "")
                else:
                    from urllib.parse import urlsplit

                    domain = (urlsplit(url).netloc or "").lower()
                    if domain and domain not in pending_domains:
                        pending_domains[domain] = candidate.get("title", "")
                if len(discovered) >= _MAX_VALIDATE:
                    break
            if len(discovered) >= _MAX_VALIDATE:
                break

        # 站点域名常见 feed 路径探测（每域名最多 4 个路径，≤6 域名）
        for domain, title in list(pending_domains.items())[:6]:
            feed_url = _guess_feed_from_domain(domain)
            if feed_url and feed_url not in seen and feed_url not in discovered:
                discovered[feed_url] = title
            if len(discovered) >= _MAX_VALIDATE:
                break

    for feed_url, title in list(discovered.items()):
        feed_title = _validate_feed(feed_url)
        if feed_title is None:
            continue
        seen.add(feed_url)
        recommendations.append(
            {
                "name": title or feed_title,
                "url": feed_url,
                "topics": [],
                "source": "search",
                "subscribed": feed_url in subscribed,
            }
        )
        if len(recommendations) >= _MAX_TOTAL_CANDIDATES:
            break

    return {
        "success": True,
        "topics": topics,
        "queries": queries,
        "recommendations": recommendations,
        "message": f"发现 {len(recommendations)} 个推荐源（内置 {sum(1 for r in recommendations if r['source'] == 'builtin')} + 搜索 {sum(1 for r in recommendations if r['source'] == 'search')}）",
    }


__all__ = ["discover_rss_sources", "load_knowledge_topics"]
