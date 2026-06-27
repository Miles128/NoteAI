from pathlib import Path

import pytest

from config import config
from sidecar.multi_source import (
    fetch_all_subscriptions,
    import_rss_feed,
    load_subscriptions,
    remove_subscription,
    save_subscription,
)


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
