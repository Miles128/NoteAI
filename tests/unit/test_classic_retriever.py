"""Tests for classic (non-vector) retrieval."""

import pytest


@pytest.fixture
def workspace_with_notes(tmp_path, monkeypatch):
    notes = tmp_path / "Notes" / "AI" / "RAG"
    notes.mkdir(parents=True)
    note = notes / "切片策略.md"
    note.write_text(
        "---\ntopic: AI > RAG\n tags: [切片, 检索]\n---\n# 切片策略\n\n"
        "文档切片是 RAG 的基础步骤。\n",
        encoding="utf-8",
    )
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "RAG_综述.md").write_text(
        "---\ntopic: AI > RAG\n---\n# RAG 综述\n\n这是 RAG 主题综述。\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("config.config.workspace_path", str(tmp_path))
    return tmp_path


def test_classic_retrieve_finds_note_by_keyword(workspace_with_notes, monkeypatch):
    from utils.fulltext_index import FullTextIndex

    monkeypatch.setattr(
        "sidecar.classic_retriever.fulltext_index",
        FullTextIndex(),
    )
    from sidecar.classic_retriever import retrieve

    results = retrieve("切片")
    types = {r.get("source_type") for r in results}
    assert "topic_tree" in types
    assert "fulltext" in types
    fulltext = next(r for r in results if r.get("source_type") == "fulltext")
    assert "切片" in fulltext.get("content", "")
    assert fulltext.get("file_path", "").endswith("切片策略.md")


def test_classic_retrieve_respects_topic_filter(workspace_with_notes, monkeypatch):
    from utils.fulltext_index import FullTextIndex

    monkeypatch.setattr(
        "sidecar.classic_retriever.fulltext_index",
        FullTextIndex(),
    )
    from sidecar.classic_retriever import retrieve

    hits = retrieve("切片", topics=["不存在的主题"])
    fulltext_hits = [r for r in hits if r.get("source_type") == "fulltext"]
    assert fulltext_hits == []
