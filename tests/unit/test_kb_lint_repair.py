from pathlib import Path
from unittest.mock import patch

import pytest

from config import config
from sidecar.kb_lint import auto_fix_broken_links, run_kb_lint


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


def test_auto_fix_broken_links_removes_wikilink(workspace: Path) -> None:
    note = workspace / "Notes" / "a.md"
    note.write_text("见 [[missing]] 与 [[target|显示]]。\n", encoding="utf-8")
    (workspace / "Notes" / "target.md").write_text("ok\n", encoding="utf-8")

    result = auto_fix_broken_links(workspace)
    assert result["success"] is True
    assert result["removed"] == 1
    text = note.read_text(encoding="utf-8")
    assert "[[missing]]" not in text
    assert "[[target|显示]]" in text or "[[target]]" in text


def test_run_kb_lint_auto_repair_clears_broken_links(workspace: Path) -> None:
    note = workspace / "Notes" / "b.md"
    note.write_text("---\ntopic: AI > 测试\n---\n\n[[ghost]]\n", encoding="utf-8")

    with patch("sidecar.kb_lint.auto_refresh_stale_surveys", return_value={"updated": 0, "topics": []}):
        report = run_kb_lint(str(workspace), auto_repair=True)

    assert report["repair"]["broken_links"]["removed"] == 1
    assert report["summary"]["broken_link"] == 0
    assert "[[ghost]]" not in note.read_text(encoding="utf-8")
