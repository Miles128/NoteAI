from pathlib import Path

import pytest
from sidecar.multi_source import import_transcript
from sidecar.schema_manager import SCHEMA_FILENAME

from config import config
from utils.link_indexer import discover_cross_refs_for_file, load_links


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    notes = d / "Notes" / "AI" / "子题"
    notes.mkdir(parents=True)
    for i, title in enumerate(["源文章", "同主题A", "同主题B", "提及源", "标签友", "远房亲戚"]):
        p = notes / f"{title}.md"
        topic = "AI > 子题" if i < 3 else "AI > 其他"
        tags = "tags: [RAG, 测试]" if i == 4 else "tags: []"
        body = f"讨论 {title} 的内容。"
        if i == 3:
            body = "这里提到了源文章的核心观点。"
        p.write_text(f"---\ntopic: {topic}\n{tags}\n---\n\n# {title}\n\n{body}\n", encoding="utf-8")
    (d / "wiki").mkdir(parents=True, exist_ok=True)
    (d / SCHEMA_FILENAME).write_text(
        "# ok\n<!-- noteai-schema-version: 2 -->\n<!-- noteai-schema-configured -->\n",
        encoding="utf-8",
    )
    config.workspace_path = str(d)
    return d


def test_discover_cross_refs_finds_related(workspace: Path) -> None:
    rel = "Notes/AI/子题/源文章.md"
    result = discover_cross_refs_for_file(rel, max_links=8, use_llm=False)
    assert result["success"] is True
    assert result["added"] >= 1
    links = load_links().get("links", [])
    outgoing = [l for l in links if l.get("from") == rel]
    assert len(outgoing) >= 1


def test_import_transcript(workspace: Path) -> None:
    tr = import_transcript("会议记录", "说话内容", source="Zoom")
    assert tr["success"] is True
    assert tr["path"].endswith(".md")


def test_create_note(workspace: Path) -> None:
    from types import SimpleNamespace

    from sidecar.handlers.files_handler import FilesHandler

    from config import config as app_config

    app_config.workspace_path = str(workspace)
    srv = SimpleNamespace(_ctx=SimpleNamespace(config=app_config, logger=None))
    h = FilesHandler(srv)
    res = h._create_note({"title": "测试笔记", "topic": ""})
    assert res["success"] is True
    assert "Notes/_未分类" in res["path"]
