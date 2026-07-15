from pathlib import Path

from sidecar.duplicate_review import get_duplicate_review, merge_duplicate_notes
from sidecar.kb_lint import run_kb_lint

from config import config


def _note(root: Path, name: str, body: str) -> str:
    path = root / "Notes" / f"{name}.md"
    path.write_text(f"---\ntopic: AI > 测试\nsource: old.pdf\n---\n\n{body}\n", encoding="utf-8")
    return str(path.relative_to(root))


def test_merge_duplicate_notes_creates_new_note_without_source_fields(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / "Notes").mkdir(parents=True)
    config.workspace_path = str(root)
    left = _note(root, "原文", "第一段内容。")
    right = _note(root, "补充", "第一段内容。\n\n第二段内容。")

    review = get_duplicate_review(root, left, right)
    assert review["success"] is True
    result = merge_duplicate_notes(root, left, right, "整合笔记")

    assert result["success"] is True
    output = root / result["output_path"]
    text = output.read_text(encoding="utf-8")
    assert "第一段内容" in text
    assert "第二段内容" in text
    assert "source:" not in text
    assert (root / left).read_text(encoding="utf-8").count("第一段内容") == 1


def test_merged_pair_is_not_reported_again_until_original_changes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / "Notes").mkdir(parents=True)
    config.workspace_path = str(root)
    left = _note(root, "原文", "这是一段足够长的重复正文。" * 15)
    right = _note(root, "副本", "这是一段足够长的重复正文。" * 15)
    first = run_kb_lint(str(root), auto_repair=False, auto_refresh_surveys=False)
    assert any(i["kind"] == "duplicate_content" for i in first["issues"])

    merge_duplicate_notes(root, left, right, "整合")
    second = run_kb_lint(str(root), auto_repair=False, auto_refresh_surveys=False)
    assert not any(i["kind"] == "duplicate_content" for i in second["issues"])
