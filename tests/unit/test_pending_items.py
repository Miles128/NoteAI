from pathlib import Path

import pytest
from sidecar.cascade_runner import record_cascade_failure
from sidecar.convert_failures import record_convert_failure
from sidecar.ingest_pipeline import save_ingest_state
from sidecar.kb_lint import filter_stale_lint_issues, run_kb_lint
from sidecar.pending_items import collect_pending_items, run_pending_cleanups_if_due

from config import config
from utils.link_indexer import load_links, save_links
from utils.topic_pending import save_pending


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
    run_pending_cleanups_if_due(str(workspace), force=True)
    items = collect_pending_items(str(workspace))
    kinds = {i.get("type") for i in items}
    assert "lint" in kinds
    assert "cascade_fail" in kinds


def test_collect_pending_auto_confirms_links_and_cleans_stale(workspace: Path) -> None:
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

    run_pending_cleanups_if_due(str(workspace), force=True)
    items = collect_pending_items(str(workspace))
    types = [i.get("type") for i in items]

    assert "link_batch" not in types
    assert "link" not in types
    assert types.count("topic") == 0
    links = {(l["from"], l["to"]): l["status"] for l in load_links()["links"]}
    # 严格判断：pending 链接保持 pending，不会因清理流程被自动确认
    assert links[("Notes/a.md", "Notes/b.md")] == "pending"
    assert links[("Notes/c.md", "Notes/b.md")] == "pending"
    assert ("Notes/missing.md", "Notes/b.md") not in links


def test_collect_pending_is_read_only_and_does_not_run_maintenance(workspace: Path, monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "sidecar.pending_items.auto_fix_broken_links",
        lambda _workspace: calls.append("repair"),
    )

    collect_pending_items(str(workspace))

    assert calls == []


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


def test_collect_pending_includes_interrupted_ingest_with_highest_priority(workspace: Path) -> None:
    save_ingest_state({"status": "cancelled", "stage": "classify", "message": "用户取消", "updated_at": 12})
    record_cascade_failure("AI > 测试", "API 超时")

    items = collect_pending_items(str(workspace))

    assert items[0]["type"] == "ingest"
    assert items[0]["action"] == "retry_ingest"
    assert items[0]["priority"] == 0


def test_exact_duplicate_content_enters_inbox(workspace: Path) -> None:
    topic_dir = workspace / "Notes" / "AI"
    topic_dir.mkdir()
    body = "这是一段完全重复的正文内容，应该被知识库整理巡检识别。" * 8
    for name in ("原文.md", "副本.md"):
        (topic_dir / name).write_text(f"---\ntopic: AI\n---\n\n{body}\n", encoding="utf-8")

    report = run_kb_lint(str(workspace), auto_repair=False)
    items = collect_pending_items(str(workspace))
    duplicates = [item for item in items if item.get("lint_kind") == "duplicate_content"]

    assert report["summary"]["duplicate_content"] == 1
    assert len(duplicates) == 1
    assert duplicates[0]["action"] == "review_duplicate"
    assert "完全重复" in duplicates[0]["message"]


def test_duplicate_issue_disappears_after_content_changes(workspace: Path) -> None:
    topic_dir = workspace / "Notes" / "AI"
    topic_dir.mkdir()
    body = "重复正文内容，需要达到检测的最小长度。" * 10
    first = topic_dir / "a.md"
    second = topic_dir / "b.md"
    first.write_text(body, encoding="utf-8")
    second.write_text(body, encoding="utf-8")
    report = run_kb_lint(str(workspace), auto_repair=False)

    second.write_text(body + "已经补充了新的独特内容。", encoding="utf-8")
    live = filter_stale_lint_issues(report["issues"], workspace)

    assert not any(issue.get("kind") == "duplicate_content" for issue in live)


def test_organization_findings_enter_inbox_with_review_actions(workspace: Path) -> None:
    finance = "股票 投资 基金 市场 估值 收益 风险 资产 配置 仓位 财务 现金流 " * 12
    cooking = "烹饪 食谱 食材 厨房 火候 调味 蒸煮 烘焙 面粉 蔬菜 锅具 香味 " * 12
    finance_dir = workspace / "Notes" / "理财"
    cooking_dir = workspace / "Notes" / "烹饪"
    finance_dir.mkdir()
    cooking_dir.mkdir()
    (finance_dir / "投资基础.md").write_text(finance + "长期投资需要控制风险。", encoding="utf-8")
    (finance_dir / "资产配置.md").write_text(finance + "资产配置需要平衡收益。", encoding="utf-8")
    (cooking_dir / "家常食谱.md").write_text(cooking + "家常菜需要掌握火候。", encoding="utf-8")
    (cooking_dir / "烘焙方法.md").write_text(cooking + "烘焙需要控制温度。", encoding="utf-8")
    (cooking_dir / "放错的投资笔记.md").write_text(finance + "基金仓位需要定期再平衡。", encoding="utf-8")

    original = "知识库入库后需要检查笔记主题、重复内容和目录位置。" * 12
    (finance_dir / "整理流程.md").write_text(original, encoding="utf-8")
    (finance_dir / "整理流程改写.md").write_text(original.replace("目录位置", "归档位置", 1), encoding="utf-8")

    report = run_kb_lint(str(workspace), auto_repair=False)
    items = collect_pending_items(str(workspace))
    near = [item for item in items if item.get("lint_kind") == "near_duplicate"]
    misplaced = [item for item in items if item.get("lint_kind") == "misplaced_note"]

    assert report["summary"]["near_duplicate"] >= 1
    assert near and near[0]["action"] == "review_duplicate"
    target = next(item for item in misplaced if item["file_path"].endswith("放错的投资笔记.md"))
    assert target["action"] == "assign_topic"
    assert target["topic"] == "理财"
    assert target["current_topic"] == "烹饪"
    assert target["suggested_score"] > 0
