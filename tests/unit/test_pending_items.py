from pathlib import Path

import pytest
from sidecar.cascade_runner import record_cascade_failure
from sidecar.convert_failures import record_convert_failure
from sidecar.kb_lint import filter_stale_lint_issues, run_kb_lint
from sidecar.pending_items import collect_pending_items
from utils.link_indexer import load_links, save_links
from utils.topic_pending import save_pending

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


def test_collect_pending_aggregates_links_and_cleans_stale(workspace: Path) -> None:
    note_a = workspace / "Notes" / "a.md"
    note_b = workspace / "Notes" / "b.md"
    note_a.write_text("---\ntopic: AI > 测试\n---\n", encoding="utf-8")
    note_b.write_text("---\ntopic: AI > 测试\n---\n", encoding="utf-8")
    note_c = workspace / "Notes" / "c.md"
    note_c.write_text("no frontmatter\n", encoding="utf-8")
    save_links(
        {
            "links": [
                {"from": "Notes/a.md", "to": "Notes/b.md", "status": "pending", "reason": "同主题"},
                {"from": "Notes/c.md", "to": "Notes/b.md", "status": "pending", "reason": "待确认"},
                {"from": "Notes/missing.md", "to": "Notes/b.md", "status": "pending", "reason": "gone"},
            ]
        }
    )
    save_pending([{"file": "Notes/gone.md", "title": "gone"}])
    (workspace / "Notes" / "resolved.md").write_text("---\ntopic: AI > 测试\n---\n", encoding="utf-8")
    save_pending(
        [
            {"file": "Notes/gone.md", "title": "gone"},
            {"file": "Notes/resolved.md", "title": "resolved"},
        ]
    )

    items = collect_pending_items(str(workspace))
    types = [i.get("type") for i in items]
    link_batch = next(i for i in items if i.get("type") == "link_batch")

    assert types.count("link_batch") == 1
    assert link_batch["count"] == 1
    assert "link" not in types
    assert types.count("topic") == 0
    links = {(l["from"], l["to"]): l["status"] for l in load_links()["links"]}
    assert links[("Notes/a.md", "Notes/b.md")] == "confirmed"
    assert links[("Notes/c.md", "Notes/b.md")] == "pending"
    assert ("Notes/missing.md", "Notes/b.md") not in links


def test_filter_stale_lint_issues(workspace: Path) -> None:
    note = workspace / "Notes" / "x.md"
    note.write_text("---\ntopic: AI > 测试\n---\n", encoding="utf-8")
    issues = [
        {"kind": "orphan_topic", "file_path": "Notes/x.md", "message": "缺少主题"},
        {"kind": "broken_link", "file_path": "Notes/missing.md", "message": "断链"},
    ]
    live = filter_stale_lint_issues(issues, workspace)
    assert live == []


def test_collect_pending_drops_missing_convert_failures(workspace: Path) -> None:
    record_convert_failure("Raw/missing.pdf", "转换失败")
    items = collect_pending_items(str(workspace))
    assert not any(i.get("type") == "convert_fail" for i in items)
