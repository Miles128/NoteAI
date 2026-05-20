"""Tests for full-text inverted index."""

import pytest
from pathlib import Path


class TestFullTextIndex:
    @pytest.fixture
    def tmp_workspace(self, tmp_path):
        notes = tmp_path / "Notes"
        notes.mkdir()
        f1 = notes / "hello.md"
        f1.write_text("# Hello World\n\nThis is a test note about Python programming.")
        f2 = notes / "guide.md"
        f2.write_text("# Python Guide\n\nPython is a great language for building application software.")
        return tmp_path

    def test_search_finds_documents(self, tmp_workspace, monkeypatch):
        from utils.fulltext_index import FullTextIndex
        monkeypatch.setattr("config.config.workspace_path", str(tmp_workspace))

        idx = FullTextIndex()
        idx.ensure_indexed()

        results = idx.search("python")
        assert len(results) >= 2  # both files mention python

        results = idx.search("application")
        assert len(results) == 1
        assert "guide" in results[0]["path"]

    def test_empty_query(self):
        from utils.fulltext_index import FullTextIndex
        idx = FullTextIndex()
        assert idx.search("") == []

    def test_mark_dirty(self, tmp_workspace, monkeypatch):
        from utils.fulltext_index import FullTextIndex
        monkeypatch.setattr("config.config.workspace_path", str(tmp_workspace))

        idx = FullTextIndex()
        idx.ensure_indexed()
        assert idx.search("hello")

        (tmp_workspace / "Notes" / "new.md").write_text("hello from new file")
        idx.mark_dirty()
        idx.ensure_indexed()

        results = idx.search("hello")
        assert len(results) == 2
