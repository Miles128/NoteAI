"""Smoke checks for static webui shell (no browser / Tauri required)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WEBUI = REPO_ROOT / "webui"
INDEX = WEBUI / "index.html"

REQUIRED_ELEMENT_IDS = frozenset(
    {
        "sidebar",
        "right-area",
        "content-panel",
        "preview-panel",
        "tiptap-editor",
        "tiptap-editor-container",
        "graph-panel",
        "ai-panel",
    }
)

REQUIRED_STATIC_ASSETS = (
    "css/variables.css",
    "css/layout.css",
    "js/main.mjs",
    "js/api.js",
    "js/preview.js",
    "js/tiptap-editor.js",
    "lib/tiptap-bundle.js",
    "d3.min.js",
    "marked.min.js",
)


def _read_index() -> str:
    assert INDEX.is_file(), "webui/index.html missing"
    return INDEX.read_text(encoding="utf-8")


def _ids_in_html(html: str) -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', html))


def _linked_paths(html: str) -> list[str]:
    paths: list[str] = []
    for pattern in (
        r'<link[^>]+href="([^"]+)"',
        r'<script[^>]+src="([^"]+)"',
    ):
        paths.extend(re.findall(pattern, html))
    return [p for p in paths if not p.startswith(("http://", "https://", "//"))]


@pytest.mark.parametrize("asset", REQUIRED_STATIC_ASSETS)
def test_required_static_asset_exists(asset: str) -> None:
    path = WEBUI / asset
    assert path.is_file(), f"missing webui asset: {asset}"


def test_index_has_core_panel_ids() -> None:
    html = _read_index()
    found = _ids_in_html(html)
    missing = REQUIRED_ELEMENT_IDS - found
    assert not missing, f"index.html missing ids: {sorted(missing)}"


def test_preview_panel_is_sibling_of_content_panel() -> None:
    """Regression: preview must not stay inside content-panel (display:none hides it)."""
    html = _read_index()
    assert re.search(
        r'</div>\s*<div class="preview-panel" id="preview-panel"',
        html,
    ), "preview-panel should be a direct sibling after content-panel closes"


def test_index_linked_local_assets_exist() -> None:
    html = _read_index()
    missing: list[str] = []
    for rel in _linked_paths(html):
        if rel.startswith("data:"):
            continue
        target = WEBUI / rel
        if not target.is_file():
            missing.append(rel)
    assert not missing, f"index.html references missing files: {missing}"
