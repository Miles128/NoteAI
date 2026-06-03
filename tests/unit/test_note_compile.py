from pathlib import Path
from unittest.mock import patch

import pytest

from config import config
from utils.link_indexer import discover_cross_refs_for_file, load_links
from utils.note_compiler import compile_note_file, rule_clean_markdown


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    notes = d / "Notes" / "AI" / "子题"
    notes.mkdir(parents=True)
    for i, title in enumerate(["源文章", "同主题A", "同主题B"]):
        p = notes / f"{title}.md"
        p.write_text(
            f"---\ntopic: AI > 子题\nsource: report.pdf\ntags: []\n---\n\n# {title}\n\n内容 {title}。\n",
            encoding="utf-8",
        )
    config.workspace_path = str(d)
    return d


def test_rule_clean_removes_page_numbers() -> None:
    raw = "正文\n\n第 3 页\n\nPage 12 of 40\n\n继续"
    cleaned = rule_clean_markdown(raw)
    assert "第 3 页" not in cleaned
    assert "Page 12" not in cleaned
    assert "继续" in cleaned


def test_compile_note_rule_only_without_api(workspace: Path) -> None:
    rel = "Notes/AI/子题/源文章.md"
    full = workspace / rel
    full.write_text(
        "---\ntopic: AI > 子题\nsource: doc.pdf\n---\n\n第 1 页\n\n# 标题\n\n"
        "我觉得超级厉害！！！这段需要足够长才能通过编译阈值检查。\n",
        encoding="utf-8",
    )
    with patch("utils.llm_utils.check_api_config", return_value=(False, "no api")):
        result = compile_note_file(rel, use_llm=True, force=True)
    assert result["success"] is True
    assert result["compiled"] is True
    text = full.read_text(encoding="utf-8")
    assert "第 1 页" not in text
    assert "source: doc.pdf" in text


def test_discover_cross_refs_no_forced_minimum(workspace: Path) -> None:
    rel = "Notes/AI/子题/源文章.md"
    result = discover_cross_refs_for_file(rel, use_llm=False, max_links=25)
    assert result["success"] is True
    links = load_links().get("links", [])
    outgoing = [l for l in links if l.get("from") == rel]
    assert len(outgoing) >= 1
    assert len(outgoing) <= 25
