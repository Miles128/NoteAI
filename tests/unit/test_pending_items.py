from pathlib import Path

import pytest
from sidecar.cascade_runner import record_cascade_failure
from sidecar.kb_lint import run_kb_lint
from sidecar.pending_items import collect_pending_items

from config import config


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes").mkdir(parents=True)
    (d / "wiki").mkdir()
    config.workspace_path = str(d)
    (d / "schema.md").write_text(
        "# s\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    return d


def test_collect_pending_includes_lint_and_cascade(workspace: Path) -> None:
    note = workspace / "Notes" / "x.md"
    note.write_text("[[missing]]\n", encoding="utf-8")
    run_kb_lint(str(workspace))
    record_cascade_failure("AI > 测试", "API 超时")
    items = collect_pending_items(str(workspace))
    kinds = {i.get("type") for i in items}
    assert "lint" in kinds
    assert "cascade_fail" in kinds
