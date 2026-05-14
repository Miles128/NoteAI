import ipaddress
import sys
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, unquote_plus, urlparse, parse_qs, urljoin

import requests
from bs4 import BeautifulSoup

MAX_RESULTS = 5
MAX_CONTENT_CHARS = 2000

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _extract_ddg_url(href: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    if "uddg" in parse_qs(parsed.query):
        return unquote_plus(parse_qs(parsed.query)["uddg"][0])
    if href.startswith("http"):
        return href
    return ""


def duckduckgo_search(query: str) -> list:
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        resp = requests.get(url, headers=_HEADERS, timeout=5, allow_redirects=True)
        if not _is_safe_url(resp.url):
            return []
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for item in soup.select(".result"):
            title_tag = item.select_one(".result__a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = _extract_ddg_url(title_tag.get("href", ""))

            snippet = ""
            snippet_tag = item.select_one(".result__snippet")
            if snippet_tag:
                snippet = snippet_tag.get_text(strip=True)

            if title and href:
                results.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                })

            if len(results) >= MAX_RESULTS:
                break

        return results
    except Exception as e:
        sys.stderr.write(f"[rag/web_search] DuckDuckGo search error: {e}\n")
        sys.stderr.flush()
        return []


def baidu_search(query: str) -> list:
    try:
        url = f"https://www.baidu.com/s?wd={quote_plus(query)}&rn={MAX_RESULTS}"
        resp = requests.get(url, headers=_HEADERS, timeout=5, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        if "安全验证" in resp.text or "验证" in resp.text[:500]:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for item in soup.select("div.result, div.c-container"):
            title_tag = item.select_one("h3 a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")

            snippet = ""
            for sel in ["span.content-right_8Zs40", ".c-abstract",
                        "div.c-abstract", ".c-span-last", "div.c-span-last",
                        "div.c-span9", "div.c-span12", "p"]:
                snippet_tag = item.select_one(sel)
                if snippet_tag:
                    text = snippet_tag.get_text(strip=True)
                    if len(text) > len(title) + 5:
                        snippet = text
                        break

            if not snippet:
                all_text = item.get_text(separator=" ", strip=True)
                remainder = all_text.replace(title, "", 1).strip()
                if len(remainder) > 20:
                    snippet = remainder[:300]

            if href and not href.startswith("http"):
                try:
                    head_resp = requests.get(
                        urljoin("https://www.baidu.com", href),
                        headers=_HEADERS, timeout=3, allow_redirects=True,
                    )
                    if _is_safe_url(head_resp.url):
                        href = str(head_resp.url)
                    else:
                        href = ""
                except Exception as e:
                    sys.stderr.write(f"[rag/web_search] resolve url {href} error: {e}\n")
                    sys.stderr.flush()

            if title and href:
                results.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                })

            if len(results) >= MAX_RESULTS:
                break

        return results
    except Exception as e:
        sys.stderr.write(f"[rag/web_search] Baidu search error: {e}\n")
        sys.stderr.flush()
        return []


def web_search(query: str) -> list:
    results = duckduckgo_search(query)
    if results:
        return results

    sys.stderr.write("[rag/web_search] DuckDuckGo returned no results, trying Baidu\n")
    sys.stderr.flush()
    return baidu_search(query)


def _is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False
        except ValueError as e:
            sys.stderr.write(f"[rag/web_search] parse ip error: {e}\n")
            sys.stderr.flush()
        if parsed.scheme not in ("http", "https"):
            return False
        return True
    except Exception:
        return False


def fetch_page_content(url: str) -> str:
    if not _is_safe_url(url):
        return ""
    try:
        from readability import Document
        from markdownify import markdownify as md

        resp = requests.get(url, headers=_HEADERS, timeout=5, allow_redirects=True)
        if not _is_safe_url(resp.url):
            return ""
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return ""

        doc = Document(html)
        title = doc.title()
        content = md(doc.summary())
        text = f"# {title}\n\n{content}"
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:MAX_CONTENT_CHARS]
    except Exception as e:
        sys.stderr.write(f"[rag/web_search] fetch {url} error: {e}\n")
        sys.stderr.flush()
        return ""


def search_and_fetch(query: str, max_pages: int = 3) -> list:
    results = web_search(query)
    if not results:
        return []

    fetched = []
    with ThreadPoolExecutor(max_workers=max_pages) as executor:
        future_map = {executor.submit(fetch_page_content, r["url"]): r for r in results[:max_pages]}
        for future in as_completed(future_map):
            r = future_map[future]
            content = future.result()
            if content:
                fetched.append({
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": r["snippet"],
                    "content": content,
                })
            else:
                fetched.append({
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": r["snippet"],
                    "content": r["snippet"],
                })
    return fetched
