from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBUI = ROOT / "webui"


def test_index_referenced_local_assets_exist() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    refs = re.findall(r"""(?:src|href)=["']([^"']+)["']""", html)

    missing = []
    for ref in refs:
        if ref.startswith(("http://", "https://", "data:", "#")):
            continue
        asset = WEBUI / ref.split("?", 1)[0]
        if not asset.exists():
            missing.append(ref)

    assert missing == []


def test_required_generated_assets_are_not_gitignored() -> None:
    required = ["webui/lib/tiptap-bundle.js"]
    result = subprocess.run(
        ["git", "check-ignore", *required],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.stdout.strip() == ""


def test_node_modules_is_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", "node_modules"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == ""


def test_job_and_status_api_methods_are_allowed_by_tauri_rpc() -> None:
    api_js = (WEBUI / "js" / "api.ts").read_text(encoding="utf-8")
    rpc_rs = (ROOT / "src-tauri" / "src" / "rpc.rs").read_text(encoding="utf-8")
    allowed_block = rpc_rs.split("static ALLOWED_PYTHON_METHODS", 1)[1].split("];", 1)[0]
    allowed = set(re.findall(r'"([a-zA-Z0-9_]+)"', allowed_block))

    required = {"get_jobs", "get_link_stats", "run_kb_lint"}
    declared = set(re.findall(r"""method:\s*['"]([^'"]+)['"]""", api_js))

    assert required <= declared
    assert required <= allowed


def test_rpc_contract_is_consistent_across_frontend_python_and_tauri() -> None:
    api_js = (WEBUI / "js" / "api.ts").read_text(encoding="utf-8")
    declared = set(re.findall(r"""method:\s*['\"]([^'\"]+)['\"]""", api_js))

    registered = set()
    for path in (ROOT / "python" / "sidecar").rglob("*.py"):
        registered.update(re.findall(r"""router\.register\(\s*['\"](\w+)['\"]""", path.read_text(encoding="utf-8")))

    rpc_rs = (ROOT / "src-tauri" / "src" / "rpc.rs").read_text(encoding="utf-8")
    allowed_block = rpc_rs.split("static ALLOWED_PYTHON_METHODS", 1)[1].split("];", 1)[0]
    allowed = set(re.findall(r'"([a-zA-Z0-9_]+)"', allowed_block))

    assert declared <= registered
    assert allowed == registered


def test_misplaced_note_uses_direct_move_or_keep_actions() -> None:
    pending_js = (WEBUI / "js" / "pending.js").read_text(encoding="utf-8")

    assign_branch = pending_js.split("} else if (item.action === 'assign_topic')", 1)[1].split("html += '</div>';", 1)[
        0
    ]
    assert 'data-action="move-suggested"' in assign_branch
    assert 'data-action="keep-current"' in assign_branch
    assert "pending-topic-select" not in assign_branch


def test_pending_view_restores_hidden_content_panel() -> None:
    """Regression: opening Inbox from note preview must reveal its parent panel."""
    pending_js = (WEBUI / "js" / "pending.js").read_text(encoding="utf-8")
    show_branch = pending_js.split("function showPendingViewContent()", 1)[1].split("function hidePendingView()", 1)[0]

    restore_parent = "contentPanel.style.display = 'flex'"
    show_pending = "pendingView.style.display = ''"
    assert restore_parent in show_branch
    assert show_pending in show_branch
    assert show_branch.index(restore_parent) < show_branch.index(show_pending)


def test_titlebar_pending_entry_remains_icon_only() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    button = html.split('id="titlebar-pending-btn"', 1)[1].split("</button>", 1)[0]

    assert "pending-icon-normal" in button
    assert "pending-icon-alert" in button
    assert "titlebar-pending-label" not in button


def test_semantic_workbench_assets_and_contract_are_wired() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    main_js = (WEBUI / "js" / "main.mjs").read_text(encoding="utf-8")
    api_js = (WEBUI / "js" / "api.ts").read_text(encoding="utf-8")
    workbench_js = (WEBUI / "js" / "semantic-workbench.ts").read_text(encoding="utf-8")

    assert 'id="titlebar-semantic-btn"' not in html
    assert 'id="semantic-workbench"' not in html
    assert 'class="sidebar-semantic-group"' in html
    assert 'id="file-tree"' in html
    assert 'id="semantic-list-pane"' in html
    assert 'id="note-list-normal"' in html
    assert 'class="semantic-detail-pane"' in html
    assert html.count("data-category=") == 6
    assert 'data-category="quality"' in html
    assert 'data-category="brief"' in html
    assert 'data-object-kind="entities"' in html
    assert 'data-object-kind="concepts"' in html
    assert "import('./semantic-workbench.ts')" in main_js
    assert "get_semantic_workbench" in api_js
    assert "get_semantic_detail" in api_js
    assert "start_semantic_full_compile" in api_js
    assert "review_semantic_conflict" in api_js
    assert "review_semantic_entity_quality" in api_js
    assert "get_semantic_topic_wiki_page" in api_js
    assert "get_topic_brief" in api_js
    assert "publish_semantic_topic_wiki_page" in api_js
    assert "data-preview-topic-page" in workbench_js
    assert "data-open-path" in workbench_js
    assert "semantic.claimTypes." in workbench_js
    assert ".catch(function(error)" in workbench_js


def test_semantic_workbench_reuses_native_three_columns() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    tree_pane = html.split('id="sidebar-pane-tree"', 1)[1].split('id="sidebar-pane-tags"', 1)[0]
    note_panel = html.split('id="note-list-panel"', 1)[1].split('id="note-list-resizer"', 1)[0]
    content_panel = html.split('id="content-panel"', 1)[1].split('id="preview-panel"', 1)[0]

    assert 'id="file-tree"' in tree_pane
    assert 'id="semantic-categories"' in tree_pane
    assert 'id="note-list-normal"' in note_panel
    assert 'id="semantic-list-pane"' in note_panel
    assert 'id="semantic-workbench-detail"' in content_panel
    assert "semantic-category-pane" not in html
