from pathlib import Path

import pytest
from sidecar.convert_failures import (
    clear_convert_failure,
    load_convert_failures,
    record_convert_batch_results,
    record_convert_failure,
)

from config import config
from utils.link_indexer import load_links, suggest_links_for_file


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    (d / "Notes" / "AI").mkdir(parents=True)
    config.workspace_path = str(d)
    return d


def test_record_and_clear_convert_failure(workspace: Path) -> None:
    record_convert_failure("doc.pdf", "格式不支持")
    items = load_convert_failures()
    assert len(items) == 1
    assert items[0]["file"] == "doc.pdf"
    clear_convert_failure("doc.pdf")
    assert load_convert_failures() == []


def test_record_convert_batch_results(workspace: Path) -> None:
    n = record_convert_batch_results(
        [
            {"success": False, "source": "a.pdf", "error": "fail"},
            {"success": True, "source": "b.pdf"},
        ]
    )
    assert n == 1
    assert len(load_convert_failures()) == 1


def test_suggest_links_same_topic(workspace: Path) -> None:
    a = workspace / "Notes" / "AI" / "a.md"
    b = workspace / "Notes" / "AI" / "b.md"
    a.write_text("---\ntopic: AI > 测试\n---\n\n内容\n", encoding="utf-8")
    b.write_text("---\ntopic: AI > 测试\n---\n\n其他\n", encoding="utf-8")
    result = suggest_links_for_file(str(a.relative_to(workspace)))
    assert result["success"] is True
    # 同主题不连双向链接：仅同属一个主题目录并不是实质关联，直接跳过
    assert result["added"] == 0
    links = load_links().get("links", [])
    # 不应生成任何链接
    assert not any(l.get("from") == str(a.relative_to(workspace)) for l in links)


def test_suggest_links_ignores_readme(workspace: Path) -> None:
    readme = workspace / "Notes" / "AI" / "README.md"
    note = workspace / "Notes" / "AI" / "note.md"
    readme.write_text("---\ntopic: AI > 测试\n---\n\n目录说明\n", encoding="utf-8")
    note.write_text("---\ntopic: AI > 测试\n---\n\n其他\n", encoding="utf-8")

    result = suggest_links_for_file(str(note.relative_to(workspace)))
    assert result["success"] is True
    links = load_links().get("links", [])
    assert not any("README.md" in (l.get("from", "") + l.get("to", "")) for l in links)

    readme_result = suggest_links_for_file(str(readme.relative_to(workspace)))
    assert readme_result["success"] is True
    assert readme_result["added"] == 0
