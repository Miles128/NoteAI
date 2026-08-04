from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sidecar.multi_source import (
    RssScheduler,
    fetch_all_subscriptions,
    import_rss_feed,
    load_subscriptions,
    remove_subscription,
    save_subscription,
)

from config import config


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes" / "_采集").mkdir(parents=True)
    config.workspace_path = str(d)
    return d


def test_save_and_list_subscription(workspace: Path) -> None:
    save_subscription(str(workspace), "https://example.com/feed.xml", "Example")
    subs = load_subscriptions(str(workspace))
    assert len(subs) == 1
    assert subs[0]["url"] == "https://example.com/feed.xml"
    assert subs[0]["name"] == "Example"


def test_remove_subscription(workspace: Path) -> None:
    save_subscription(str(workspace), "https://example.com/a.xml")
    remove_subscription(str(workspace), "https://example.com/a.xml")
    assert load_subscriptions(str(workspace)) == []


def test_import_rss_feed_without_fetch(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> None:
    atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Test Entry</title>
    <link href="https://example.com/post-1"/>
    <summary>Hello RSS</summary>
  </entry>
</feed>"""

    class FakeResp:
        content = atom

        def raise_for_status(self):
            return None

    monkeypatch.setattr("sidecar.multi_source.requests.get", lambda *a, **k: FakeResp())
    monkeypatch.setattr(
        "utils.network_security.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )

    result = import_rss_feed("https://example.com/feed.xml", max_items=5, fetch_articles=False)
    assert result["success"] is True
    assert result["imported"] == 1
    saved = list((workspace / "Notes" / "_采集").glob("*.md"))
    assert len(saved) == 1
    assert "Hello RSS" in saved[0].read_text(encoding="utf-8")


def test_fetch_all_subscriptions_empty(workspace: Path) -> None:
    result = fetch_all_subscriptions(str(workspace))
    assert result["success"] is True
    assert result["results"] == []


def test_save_subscription_rejects_invalid_url(workspace: Path) -> None:
    result = save_subscription(str(workspace), "not-a-url")
    assert result["success"] is False
    assert load_subscriptions(str(workspace)) == []


def test_save_subscription_fetches_feed_title(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> None:
    import xml.etree.ElementTree as ET

    root = ET.fromstring("<rss><channel><title>My Feed</title></channel></rss>")
    monkeypatch.setattr("sidecar.multi_source._fetch_rss", lambda url: root)

    result = save_subscription(str(workspace), "https://example.com/feed.xml")
    assert result["success"] is True
    subs = load_subscriptions(str(workspace))
    assert len(subs) == 1
    assert subs[0]["name"] == "My Feed"


def test_rss_scheduler_is_due() -> None:
    now = datetime.now(timezone.utc)
    assert RssScheduler._is_due({"url": "x"})  # 从未拉取过
    assert not RssScheduler._is_due({"url": "x", "last_fetched": now.isoformat(), "interval_minutes": 30})
    old = (now - timedelta(minutes=31)).isoformat()
    assert RssScheduler._is_due({"url": "x", "last_fetched": old, "interval_minutes": 30})
