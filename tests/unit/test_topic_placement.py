from __future__ import annotations

from pathlib import Path

from sidecar.organization_audit import find_misplaced_notes
from sidecar.textutils import parse_frontmatter
from sidecar.topic_placement import auto_move_misplaced_notes, keep_note_in_current_topic

from config import config


def _note(root: Path, topic: str, name: str, body: str = "正文") -> Path:
    folder = root / "Notes" / topic
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_text(f"---\ntopic: {topic}\n---\n\n{body}\n", encoding="utf-8")
    return path


def test_score_at_threshold_is_moved_before_indexing(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    source = _note(root, "当前主题", "待移动")
    config.workspace_path = str(root)
    monkeypatch.setattr(config, "auto_topic", True)
    monkeypatch.setattr(config, "topic_auto_assign_threshold", 0.62)
    monkeypatch.setattr(
        "sidecar.organization_audit.find_misplaced_notes",
        lambda _root: [
            {
                "file_path": "Notes/当前主题/待移动.md",
                "current_topic": "当前主题",
                "suggested_topic": "目标主题",
                "current_score": 0.1,
                "suggested_score": 0.62,
            }
        ],
    )

    result = auto_move_misplaced_notes(root)

    target = root / "Notes" / "目标主题" / "待移动.md"
    assert result["success"] is True
    assert len(result["moved"]) == 1
    assert not source.exists()
    assert target.exists()
    meta, _ = parse_frontmatter(target.read_text(encoding="utf-8"))
    assert meta["topic"] == "目标主题"


def test_score_below_threshold_stays_pending(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    source = _note(root, "当前主题", "暂不移动")
    config.workspace_path = str(root)
    monkeypatch.setattr(config, "auto_topic", True)
    monkeypatch.setattr(config, "topic_auto_assign_threshold", 0.63)
    monkeypatch.setattr(
        "sidecar.organization_audit.find_misplaced_notes",
        lambda _root: [
            {
                "file_path": "Notes/当前主题/暂不移动.md",
                "current_topic": "当前主题",
                "suggested_topic": "目标主题",
                "current_score": 0.1,
                "suggested_score": 0.62,
            }
        ],
    )

    result = auto_move_misplaced_notes(root)

    assert result["moved"] == []
    assert source.exists()


def test_keep_decision_hides_unchanged_finding_and_expires_after_edit(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    finance = "股票 投资 基金 市场 估值 收益 风险 资产 配置 仓位 财务 现金流 " * 12
    cooking = "烹饪 食谱 食材 厨房 火候 调味 蒸煮 烘焙 面粉 蔬菜 锅具 香味 " * 12
    _note(root, "理财", "投资基础", finance + "长期投资需要控制风险。")
    _note(root, "理财", "资产配置", finance + "资产配置需要平衡收益。")
    _note(root, "烹饪", "家常食谱", cooking + "家常菜需要掌握火候。")
    _note(root, "烹饪", "烘焙方法", cooking + "烘焙需要控制温度。")
    misplaced = _note(root, "烹饪", "放错的投资笔记", finance + "基金仓位需要定期再平衡。")

    finding = next(item for item in find_misplaced_notes(root) if item["file_path"].endswith(misplaced.name))
    result = keep_note_in_current_topic(
        root,
        finding["file_path"],
        finding["current_topic"],
        finding["suggested_topic"],
    )

    assert result["success"] is True
    assert not any(item["file_path"].endswith(misplaced.name) for item in find_misplaced_notes(root))

    misplaced.write_text(misplaced.read_text(encoding="utf-8") + "\n新增投资分析。\n", encoding="utf-8")
    assert any(item["file_path"].endswith(misplaced.name) for item in find_misplaced_notes(root))
