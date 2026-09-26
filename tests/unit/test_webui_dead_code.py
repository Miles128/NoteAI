from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBUI = ROOT / "webui"
JS_DIR = WEBUI / "js"

# 瘦身批次中删除的 HTML id：不得再出现在 HTML 或 JS 的 getElementById 字面量中。
REMOVED_IDS = frozenset(
    {
        "integrate-btn",
        "integration-hint",
        "settings-raw-convert-btn",
        "settings-raw-convert-status",
        "ingest-pipeline-retry",
        "pending-cascade-retry-all-btn",
        "pending-cascade-section",
        "pending-cascade-list",
        "pending-cascade-count",
        "topic-files-panel",
        "topic-pending-panel",
        "ai-suggestion-panel",
        "conv-ai-toggle",
        "conv-target-format",
        "conv-progress",
        "web-urls",
        "web-ai-toggle",
        "web-include-images",
        "about-panel",
        "log-panel",
        "sidebar-pane-tags",
        "sidebar-pane-graph",
        "sidebar-footer-tags",
        "sidebar-footer-graph",
        "extract-topics-btn",
        "topic-list",
        "topic-count",
        "integration-progress-fill",
        "integration-status",
        "btn-auto-tag",
        "btn-add-tag",
        "tag-input-field",
        "tag-input-cancel",
        "tag-input-confirm",
        "sidebar-tag-input",
        "sidebar-tags",
        "sidebar-graph",
        "sidebar-status-tags",
        "sidebar-status-graph",
    }
)

# 后端已注销、前端已摘除的 RPC 方法名：api.ts / rpc.rs / Python 注册三处均不得再现。
REMOVED_RPC_METHODS = frozenset(
    {
        "ai_topic_analyze",
        "ai_topic_survey",
        "apply_topic_suggestion",
        "batch_auto_assign_topics",
        "get_survey_overview",
        "move_file_to_topic",
        "rename_topic",
        "start_file_conversion",
        "start_note_integration",
        "sync_wiki_with_files",
        "toggle_survey",
        "extract_topics",
        "fix_survey_topics",
    }
)

# 已删除的 JS 符号（含全局别名与模块方法名）：源码中不得再引用。
REMOVED_JS_SYMBOLS = frozenset(
    {
        "startNoteIntegration",
        "startFileConversion",
        "ConverterModule",
        "closeLogPanel",
        "updateIntegrateBtnState",
        "retryAllPendingSurveys",
        "loadSavedConfig",
        "updateWebAIStatus",
        "updateConvAIStatus",
        "getSurveyOverview",
        "toggleSurvey",
        "batchAutoAssignTopics",
        "syncWikiWithFiles",
        "aiTopicAnalyze",
        "aiTopicSurvey",
        "applyTopicSuggestion",
        "showLog",
        "IntegratorModule",
        "loadTagsView",
        "doAutoTag",
        "onShowAddTagInput",
        "showGraphHomeView",
        "markSidebarTreeDirty",
        "consumeSidebarTreeDirty",
        "lastTagsData",
        "loadTopicPendingPanel",
        "onCandidateClick",
        "hasTopicPending",
    }
)


def _js_sources() -> list[Path]:
    paths: list[Path] = []
    for pattern in ("*.ts", "*.mjs", "*.js"):
        for path in sorted(JS_DIR.glob(pattern)):
            if path.name in {"storage.bundle.js", "error-handler.bundle.js"}:
                continue
            paths.append(path)
    return paths


def test_removed_ids_absent_from_html_and_js() -> None:
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    js_blob = "\n".join(p.read_text(encoding="utf-8") for p in _js_sources())

    for rid in REMOVED_IDS:
        assert f'id="{rid}"' not in html, f"removed id still in index.html: {rid}"
        assert f"getElementById('{rid}')" not in js_blob, f"removed id still queried: {rid}"
        assert f'getElementById("{rid}")' not in js_blob, f"removed id still queried: {rid}"


def test_removed_rpc_methods_fully_unwired() -> None:
    api_ts = (JS_DIR / "api.ts").read_text(encoding="utf-8")
    declared = set(re.findall(r"""method:\s*['"]([^'"]+)['"]""", api_ts))

    rpc_rs = (ROOT / "src-tauri" / "src" / "rpc.rs").read_text(encoding="utf-8")
    allowed_block = rpc_rs.split("static ALLOWED_PYTHON_METHODS", 1)[1].split("];", 1)[0]
    allowed = set(re.findall(r'"([a-zA-Z0-9_]+)"', allowed_block))

    registered: set[str] = set()
    for path in (ROOT / "python" / "sidecar").rglob("*.py"):
        registered.update(re.findall(r"""router\.register\(\s*['"](\w+)['"]""", path.read_text(encoding="utf-8")))

    for method in REMOVED_RPC_METHODS:
        assert method not in declared, f"api.ts still declares {method}"
        assert method not in allowed, f"rpc.rs still allows {method}"
        assert method not in registered, f"Python still registers {method}"


def test_removed_js_symbols_absent_from_sources() -> None:
    for path in _js_sources():
        text = path.read_text(encoding="utf-8")
        for sym in REMOVED_JS_SYMBOLS:
            assert sym not in text, f"{sym} still referenced in {path.name}"


def test_converter_module_is_fully_removed() -> None:
    assert not (JS_DIR / "converter.ts").exists()
    main_mjs = (JS_DIR / "main.mjs").read_text(encoding="utf-8")
    assert "converter.ts" not in main_mjs
    assert "startFileConversion" not in main_mjs


def test_extract_topics_entry_point_removed() -> None:
    """D1 已删除 tab-1 整合页与 extract_topics 全链。"""
    html = (WEBUI / "index.html").read_text(encoding="utf-8")
    main_mjs = (JS_DIR / "main.mjs").read_text(encoding="utf-8")

    assert not (JS_DIR / "integrator.ts").exists()
    assert not (JS_DIR / "tags.ts").exists()
    assert 'id="tab-1"' not in html
    assert "integrator.ts" not in main_mjs
    assert "tags.ts" not in main_mjs
    assert 'id="extract-topics-btn"' not in html
    assert 'onclick="extractTopics()"' not in html
