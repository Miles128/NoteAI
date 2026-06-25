import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.modules["pymilvus"] = MagicMock()

from sidecar.rag.index import (
    _bm25_scores,
    _build_bm25_index,
    build_index,
    delete_by_file,
    _escape_filter_value,
    fetch_chunks_by_file,
    hybrid_search,
    index_exists,
    _is_bm25_index,
    _purge_stale_sparse_ids,
    _sparse_index_path,
    filter_usable_chunks,
    is_usable_chunk,
)


class TestIsUsableChunk:
    def test_content_present(self):
        assert is_usable_chunk({"content": "hello world"}) is True

    def test_empty_content(self):
        assert is_usable_chunk({"content": ""}) is False

    def test_whitespace_only(self):
        assert is_usable_chunk({"content": "   \t\n  "}) is False

    def test_missing_content_key(self):
        assert is_usable_chunk({}) is False

    def test_none_content(self):
        assert is_usable_chunk({"content": None}) is False


class TestFilterUsableChunks:
    def test_mixed_results(self):
        results = [
            {"content": "valid"},
            {"content": ""},
            {"content": "  "},
            {"content": "another valid"},
            {},
        ]
        filtered = filter_usable_chunks(results)
        assert len(filtered) == 2
        assert filtered[0]["content"] == "valid"
        assert filtered[1]["content"] == "another valid"

    def test_all_usable(self):
        results = [{"content": "a"}, {"content": "b"}]
        assert filter_usable_chunks(results) == results

    def test_none_usable(self):
        results = [{"content": ""}, {"content": "  "}, {}]
        assert filter_usable_chunks(results) == []

    def test_empty_list(self):
        assert filter_usable_chunks([]) == []


class TestPurgeStaleSparseIds:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "ws"
        ws.mkdir()
        idx_dir = ws / ".noteai" / "rag_index"
        idx_dir.mkdir(parents=True)
        return ws

    def _write_sparse_index(self, workspace: Path, data: dict):
        path = _sparse_index_path(str(workspace))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _read_sparse_index(self, workspace: Path) -> dict:
        path = _sparse_index_path(str(workspace))
        return json.loads(path.read_text(encoding="utf-8"))

    def test_removes_stale_ids(self, workspace: Path):
        data = {
            "chunk_a": {"10": 0.5},
            "chunk_b": {"20": 0.3},
            "chunk_c": {"30": 0.7},
        }
        self._write_sparse_index(workspace, data)
        _purge_stale_sparse_ids(str(workspace), ["chunk_a", "chunk_c"])
        remaining = self._read_sparse_index(workspace)
        assert "chunk_a" not in remaining
        assert "chunk_c" not in remaining
        assert "chunk_b" in remaining

    def test_no_change_when_ids_absent(self, workspace: Path):
        data = {"chunk_a": {"10": 0.5}}
        self._write_sparse_index(workspace, data)
        _purge_stale_sparse_ids(str(workspace), ["chunk_x", "chunk_y"])
        remaining = self._read_sparse_index(workspace)
        assert remaining == data

    def test_no_file_no_error(self, workspace: Path):
        _purge_stale_sparse_ids(str(workspace), ["chunk_a"])

    def test_empty_stale_list(self, workspace: Path):
        data = {"chunk_a": {"10": 0.5}}
        self._write_sparse_index(workspace, data)
        _purge_stale_sparse_ids(str(workspace), [])
        remaining = self._read_sparse_index(workspace)
        assert remaining == data

    def test_removes_stale_ids_from_bm25_index(self, workspace: Path):
        data = _build_bm25_index(
            [{"id": "chunk_a"}, {"id": "chunk_b"}],
            [
                {"lexical_weights": {"alpha": 2, "beta": 1}},
                {"lexical_weights": {"beta": 1}},
            ],
        )
        self._write_sparse_index(workspace, data)
        _purge_stale_sparse_ids(str(workspace), ["chunk_a"])
        remaining = self._read_sparse_index(workspace)
        assert _is_bm25_index(remaining)
        assert "chunk_a" not in remaining["docs"]
        assert "chunk_b" in remaining["docs"]
        assert remaining["doc_count"] == 1
        assert "alpha" not in remaining["df"]


class TestBm25Index:
    def test_builds_bm25_index_from_lexical_counts(self):
        index = _build_bm25_index(
            [{"id": "chunk_a"}, {"id": "chunk_b"}],
            [
                {"lexical_weights": {"zvec": 2, "rag": 1}},
                {"lexical_weights": {"rag": 3}},
            ],
        )

        assert _is_bm25_index(index)
        assert index["doc_count"] == 2
        assert index["df"]["zvec"] == 1
        assert index["df"]["rag"] == 2
        assert index["docs"]["chunk_a"]["doc_len"] == 3

    def test_bm25_scores_prefer_more_relevant_document(self):
        index = _build_bm25_index(
            [{"id": "chunk_a"}, {"id": "chunk_b"}],
            [
                {"lexical_weights": {"zvec": 3, "rag": 1}},
                {"lexical_weights": {"rag": 3}},
            ],
        )

        scores = _bm25_scores({"zvec": 1}, index)

        assert scores["chunk_a"] == 1.0
        assert "chunk_b" not in scores


class TestZvecBackend:
    @pytest.fixture
    def workspace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setenv("NOTEAI_VECTOR_STORE", "zvec")
        return ws

    def test_build_search_fetch_and_delete(self, workspace: Path):
        chunks = [
            {
                "id": "chunk_a",
                "content": "zvec 是 本地 向量 数据库",
                "file_path": "Notes/a.md",
                "topic": "AI",
                "tags": ["zvec"],
                "section_title": "A",
            },
            {
                "id": "chunk_b",
                "content": "BM25 适合 关键词 检索",
                "file_path": "Notes/b.md",
                "topic": "Search",
                "tags": ["bm25"],
                "section_title": "B",
            },
        ]
        embeddings = [
            {"dense_vec": [1.0] + [0.0] * 511, "lexical_weights": {"zvec": 2, "本地": 1}},
            {"dense_vec": [0.0, 1.0] + [0.0] * 510, "lexical_weights": {"BM25": 2, "关键词": 1}},
        ]

        result = build_index(str(workspace), chunks, embeddings)

        assert result["success"] is True
        assert result["backend"] == "zvec"
        assert index_exists(str(workspace)) is True

        hits = hybrid_search(str(workspace), [1.0] + [0.0] * 511, {"zvec": 1}, top_k=5)
        assert hits[0]["id"] == "chunk_a"
        assert hits[0]["sparse_score"] > 0

        rows = fetch_chunks_by_file(str(workspace), "Notes/a.md")
        assert rows[0]["id"] == "chunk_a"

        delete_by_file(str(workspace), "Notes/a.md")
        hits_after_delete = hybrid_search(str(workspace), [1.0] + [0.0] * 511, {"zvec": 1}, top_k=5)
        assert all(hit["id"] != "chunk_a" for hit in hits_after_delete)


class TestEscapeFilterValue:
    def test_no_special_chars(self):
        assert _escape_filter_value("hello") == "hello"

    def test_backslash(self):
        assert _escape_filter_value("path\\to\\file") == "path\\\\to\\\\file"

    def test_double_quote(self):
        assert _escape_filter_value('say "hi"') == 'say \\"hi\\"'

    def test_backslash_and_quote(self):
        assert _escape_filter_value('path\\to\\"file"') == 'path\\\\to\\\\\\"file\\"'

    def test_empty_string(self):
        assert _escape_filter_value("") == ""
