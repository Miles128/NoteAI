from __future__ import annotations

from pathlib import Path

from sidecar.organization_audit import find_misplaced_notes, find_near_duplicates


def _write_note(root: Path, topic: str, name: str, body: str) -> Path:
    folder = root / "Notes" / topic
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.md"
    path.write_text(f"---\ntopic: {topic}\n---\n\n{body}\n", encoding="utf-8")
    return path


def test_near_duplicate_detects_small_edits_but_excludes_exact_copies(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    base = (
        "知识库整理需要先读取新笔记的标题、正文和标签，再判断目标主题。"
        "系统只给出高置信建议，所有移动操作都要经过用户确认。"
        "近似重复检测用于发现内容相同但措辞略有变化的副本。"
    ) * 5
    _write_note(root, "产品", "原文", base)
    _write_note(root, "产品", "轻微改写", base.replace("目标主题", "合适主题", 1))
    _write_note(root, "产品", "完全副本", base)
    _write_note(root, "产品", "不同内容", "烹饪时需要控制火候和水分，食材应当保持新鲜。" * 12)

    results = find_near_duplicates(root)

    assert any(item["file_path"].endswith("轻微改写.md") for item in results)
    assert not any(item["file_path"].endswith("完全副本.md") for item in results)
    assert not any(item["file_path"].endswith("不同内容.md") for item in results)


def test_misplaced_note_prefers_established_semantic_topic(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    finance = "股票 投资 基金 市场 估值 收益 风险 资产 配置 仓位 财务 现金流 " * 12
    cooking = "烹饪 食谱 食材 厨房 火候 调味 蒸煮 烘焙 面粉 蔬菜 锅具 香味 " * 12
    _write_note(root, "理财", "投资基础", finance + "长期投资需要控制风险。")
    _write_note(root, "理财", "资产配置", finance + "资产配置需要平衡收益。")
    _write_note(root, "烹饪", "家常食谱", cooking + "家常菜需要掌握火候。")
    _write_note(root, "烹饪", "烘焙方法", cooking + "烘焙需要控制温度。")
    _write_note(root, "烹饪", "放错的投资笔记", finance + "基金仓位需要定期再平衡。")

    results = find_misplaced_notes(root)

    misplaced = next(item for item in results if item["file_path"].endswith("放错的投资笔记.md"))
    assert misplaced["current_topic"] == "烹饪"
    assert misplaced["suggested_topic"] == "理财"
    assert not any(item["file_path"].endswith("家常食谱.md") for item in results)
