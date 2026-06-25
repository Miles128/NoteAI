"""Smoke checks for static webui shell (no browser / Tauri required)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WEBUI = REPO_ROOT / "webui"
INDEX = WEBUI / "index.html"
RPC_RS = REPO_ROOT / "src-tauri" / "src" / "rpc.rs"

REQUIRED_ELEMENT_IDS = frozenset({
    "sidebar",
    "file-list-sidebar",
    "right-area",
    "content-panel",
    "preview-panel",
    "tiptap-editor",
    "tiptap-editor-container",
    "graph-panel",
    "ai-panel",
    "file-tree",
    "note-list",
})

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


def test_legacy_sidebar_views_are_removed() -> None:
    html = _read_index()
    removed = (
        'class="titlebar-btn tab-btn sidebar-view-btn',
        'data-sidebar="tags"',
        'data-sidebar="graph"',
        'id="sidebar-pane-tags"',
        'id="sidebar-pane-graph"',
        'id="sidebar-footer-tags"',
        'id="sidebar-footer-graph"',
        'id="pending-links-panel"',
        'id="btn-discover-links"',
    )
    present = [snippet for snippet in removed if snippet in html]
    assert not present, f"legacy sidebar UI should be removed: {present}"
    assert 'id="sidebar-pane-tree"' in html
    assert 'id="titlebar-graph-btn"' in html


def test_four_column_shell_has_collapsible_left_columns() -> None:
    html = _read_index()
    assert 'id="sidebar"' in html
    assert 'id="file-list-sidebar"' in html
    assert 'id="content-panel"' in html
    assert 'id="ai-panel"' in html
    assert 'onclick="toggleSidebar()"' in html
    assert 'onclick="toggleFileListSidebar()"' in html


def test_right_panel_has_rag_cli_switch_and_cli_choices() -> None:
    html = _read_index()
    assert 'data-ai-mode="rag"' in html
    assert 'data-ai-mode="cli"' in html
    assert 'id="ai-cli-agent-select"' in html
    assert 'id="ai-input"' in html
    assert 'Claude Code' in html
    assert 'Codex CLI' in html
    assert 'OpenCode' in html
    assert 'KimiCode' in html


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


def test_webui_python_rpc_calls_are_allowlisted() -> None:
    rpc_text = RPC_RS.read_text(encoding="utf-8")
    allowlist_block = rpc_text.split("ALLOWED_PYTHON_METHODS", 1)[1].split("];", 1)[0]
    allowed = set(re.findall(r'"([a-zA-Z0-9_]+)"', allowlist_block))

    called: set[str] = set()
    for js_file in (WEBUI / "js").glob("*.js"):
        called.update(re.findall(r"""pyCall\(['"]([^'"]+)""", js_file.read_text(encoding="utf-8")))

    missing = sorted(called - allowed)
    assert not missing, f"webui pyCall methods missing from Rust allowlist: {missing}"
