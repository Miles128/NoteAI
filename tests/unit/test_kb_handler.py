from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sidecar.handlers.kb_handler import KbHandler
from sidecar.kb_lint import run_kb_lint

from config import config

_SCHEMA_OK = (
    "ai_may_edit_wiki: true\n"
    "ai_may_edit_notes: true\n"
    "<!-- noteai-schema-version: 2 -->\n"
    "<!-- noteai-schema-configured -->\n"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes").mkdir(parents=True)
    (d / "wiki").mkdir()
    (d / "schema.md").write_text(_SCHEMA_OK, encoding="utf-8")
    config.workspace_path = str(d)
    return d


@pytest.fixture
def kb_handler() -> KbHandler:
    server = SimpleNamespace(
        _ctx=SimpleNamespace(config=config, logger=None),
        _send_response=lambda _msg: None,
    )
    return KbHandler(server)


def test_run_kb_lint_rpc(workspace: Path, kb_handler: KbHandler) -> None:
    note = workspace / "Notes" / "orphan.md"
    note.write_text("[[不存在的链接]]\n", encoding="utf-8")
    with patch("sidecar.kb_lint.auto_refresh_stale_surveys", return_value={"updated": 0, "topics": []}):
        result = kb_handler._run_kb_lint({})
    assert result["success"] is True
    assert result["summary"]["broken_link"] == 0
    assert "[[不存在的链接]]" not in note.read_text(encoding="utf-8")
    assert result["summary"]["orphan_topic"] >= 1


def test_get_lint_report_cached(workspace: Path, kb_handler: KbHandler) -> None:
    run_kb_lint(str(workspace))
    cached = kb_handler._get_lint_report({})
    assert cached["success"] is True
    assert cached.get("cached") is True


def test_archive_chat_answer_rpc(workspace: Path, kb_handler: KbHandler) -> None:
    result = kb_handler._archive_chat_answer(
        {
            "question": "Q",
            "answer": "A",
            "target": "note",
        }
    )
    assert result["success"] is True
    assert (workspace / "Notes" / "小忆对话").exists()
