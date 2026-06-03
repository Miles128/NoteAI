import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.modules["pymilvus"] = MagicMock()

from sidecar.rag.index import (
    _escape_filter_value,
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
