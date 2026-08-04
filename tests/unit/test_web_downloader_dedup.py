"""URL-level dedup for web downloads (P0 collection loop)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from modules.web_downloader import WebDownloader, existing_source_urls, normalize_source_url


def test_normalize_source_url_drops_fragment_tracking_and_slash() -> None:
    assert normalize_source_url("https://example.com/a/?utm_source=x#frag") == "https://example.com/a"
    assert normalize_source_url("https://example.com/a/") == "https://example.com/a"
    assert normalize_source_url("http://EXAMPLE.com/A") == "http://example.com/a"
    assert normalize_source_url("https://example.com/a?utm_source=x&keep=1") == "https://example.com/a?keep=1"
    assert normalize_source_url("https://example.com/") == "https://example.com/"
    assert normalize_source_url("") == ""
    assert normalize_source_url("not a url") == "not a url"


def test_existing_source_urls_collects_frontmatter(tmp_path: Path) -> None:
    notes = tmp_path / "Notes" / "主题"
    notes.mkdir(parents=True)
    (notes / "a.md").write_text(
        '---\ntitle: a\nsource_url: "https://example.com/a/?utm_source=tt"\n---\nbody\n', encoding="utf-8"
    )
    (notes / "b.md").write_text("---\ntitle: b\n---\nbody\n", encoding="utf-8")
    found = existing_source_urls(str(tmp_path))
    assert found == {"https://example.com/a"}


def test_download_batch_skips_existing_source(tmp_path: Path) -> None:
    notes = tmp_path / "Notes"
    notes.mkdir(parents=True)
    (notes / "old.md").write_text(
        '---\ntitle: old\nsource_url: "https://example.com/dup"\n---\nbody\n', encoding="utf-8"
    )
    downloader = WebDownloader()
    with (
        patch.object(WebDownloader, "download_article") as fake,
        patch("utils.tag_extractor.save_tags_md"),
    ):
        fake.return_value = {
            "success": True,
            "url": "https://example.com/dup",
            "title": "Dup",
            "content": "x",
            "html_content": "",
        }
        results = downloader.download_batch(["https://example.com/dup"], str(tmp_path))

    assert len(results) == 1
    assert results[0]["duplicate"] is True
    assert not (notes / "Dup.md").exists()
    fake.assert_not_called()


def test_download_batch_skips_duplicate_within_batch(tmp_path: Path) -> None:
    downloader = WebDownloader()
    with (
        patch.object(WebDownloader, "download_article") as fake,
        patch("utils.tag_extractor.save_tags_md"),
    ):
        fake.return_value = {
            "success": True,
            "url": "https://example.com/b",
            "title": "B",
            "content": "x",
            "html_content": "",
        }
        results = downloader.download_batch(
            ["https://example.com/b?utm_source=x", "https://example.com/b"], str(tmp_path)
        )

    assert len(results) == 2
    assert results[0]["success"] is True
    assert results[1]["duplicate"] is True
    assert fake.call_count == 1
