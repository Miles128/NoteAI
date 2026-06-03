from pathlib import Path

import pytest

from config import config
from utils.wiki_manager import sync_wiki_with_files


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    notes = d / "Notes" / "AI" / "基础"
    notes.mkdir(parents=True)
    (d / "wiki").mkdir()
    (notes / "笔记.md").write_text("# 标题\n\n这是摘要第一句。\n", encoding="utf-8")
    (d / "schema.md").write_text(
        "<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    config.workspace_path = str(d)
    return d


def test_sync_wiki_includes_topic_summary(workspace: Path) -> None:
    result = sync_wiki_with_files()
    assert result["success"] is True
    wiki = (workspace / "wiki" / "WIKI.md").read_text(encoding="utf-8")
    assert "> " in wiki
    assert "摘要" in wiki or "标题" in wiki
