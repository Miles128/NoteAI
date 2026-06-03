from pathlib import Path

import pytest

from config import config
from sidecar.kb_lint import log_lint_report


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    (d / "wiki").mkdir()
    config.workspace_path = str(d)
    return d


def test_log_lint_report_writes_per_issue(workspace: Path) -> None:
    report = {
        "issues": [
            {
                "kind": "broken_link",
                "file_path": "Notes/a.md",
                "message": "双向链接目标不存在: [[missing]]",
            },
            {
                "kind": "orphan_topic",
                "file_path": "Notes/b.md",
                "message": "缺少主题",
            },
        ],
        "summary": {"total": 2, "broken_link": 1, "orphan_topic": 1},
    }
    log_lint_report(report)
    text = (workspace / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "断链: Notes/a.md" in text
    assert "缺主题: Notes/b.md" in text
    assert "健康检查: 2 项" in text


def test_log_lint_report_no_issues(workspace: Path) -> None:
    log_lint_report({"issues": [], "summary": {"total": 0}})
    text = (workspace / "wiki" / "log.md").read_text(encoding="utf-8")
    assert "无问题" in text
