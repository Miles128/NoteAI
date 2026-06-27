from pathlib import Path

import numpy as np
import pytest
import zvec
from sidecar.rag.index import (
    _empty_metadata,
    _filter_candidates,
    _load_metadata,
    _save_metadata,
    _update_metadata_index,
    bm25_index_ready,
    build_index,
    clear_bm25_cache,
    ensure_bm25_index,
    filter_usable_chunks,
    hybrid_search,
    index_exists,
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


class TestMetadataIndex:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "ws"
        ws.mkdir()
        return ws

    def test_empty_metadata(self, workspace: Path):
        assert index_exists(str(workspace)) is False

    def test_update_metadata_add(self, workspace: Path):
        meta = _empty_metadata()
        chunk = {
            "id": "c1",
            "file_path": "Notes/a/b/c.md",
            "topic": "a > b",
            "tags": ["tag1", "tag2"],
        }
        _update_metadata_index(meta, chunk, mode="add")
        assert "c1" in meta["topics"]["a > b"]
        assert "c1" in meta["tags"]["tag1"]
        assert "c1" in meta["tags"]["tag2"]
        assert "c1" in meta["files"]["Notes/a/b/c.md"]

    def test_update_metadata_remove(self, workspace: Path):
        meta = _empty_metadata()
        chunk = {"id": "c1", "file_path": "x.md", "topic": "a", "tags": ["t1"]}
        _update_metadata_index(meta, chunk, mode="add")
        _update_metadata_index(meta, chunk, mode="remove")
        assert meta["topics"] == {}
        assert meta["tags"] == {}
        assert meta["files"] == {}

    def test_save_and_load_metadata(self, workspace: Path):
        meta = _empty_metadata()
        meta["topics"]["t"] = ["c1"]
        _save_metadata(str(workspace), meta)
        loaded = _load_metadata(str(workspace))
        assert loaded["topics"]["t"] == ["c1"]

    def test_filter_candidates(self, workspace: Path):
        meta = _empty_metadata()
        c1 = {"id": "c1", "file_path": "x.md", "topic": "a > b", "tags": ["t1"]}
        c2 = {"id": "c2", "file_path": "y.md", "topic": "a > c", "tags": ["t2"]}
        c3 = {"id": "c3", "file_path": "z.md", "topic": "a > b", "tags": ["t2"]}
        for c in [c1, c2, c3]:
            _update_metadata_index(meta, c, mode="add")
        _save_metadata(str(workspace), meta)

        assert _filter_candidates(str(workspace), ["a > b"], None) == {"c1", "c3"}
        assert _filter_candidates(str(workspace), None, ["t2"]) == {"c2", "c3"}
        assert _filter_candidates(str(workspace), ["a > b"], ["t2"]) == {"c3"}


class TestBuildAndSearch:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "ws"
        ws.mkdir()
        return ws

    def test_build_index_and_search(self, workspace: Path):
        chunks = [
            {
                "id": "c1",
                "content": "人工智能在医疗诊断中的应用",
                "file_path": "Notes/AI/医疗.md",
                "topic": "AI > 医疗",
                "tags": ["AI", "医疗"],
                "section_title": "",
            },
            {
                "id": "c2",
                "content": "深度学习用于图像识别",
                "file_path": "Notes/AI/图像.md",
                "topic": "AI > 图像",
                "tags": ["AI", "CV"],
                "section_title": "",
            },
            {
                "id": "c3",
                "content": "Python 编程入门指南",
                "file_path": "Notes/编程/Python.md",
                "topic": "编程 > Python",
                "tags": ["Python"],
                "section_title": "",
            },
        ]
        embeddings = [
            {"dense_vec": np.random.rand(512).astype(np.float32).tolist()},
            {"dense_vec": np.random.rand(512).astype(np.float32).tolist()},
            {"dense_vec": np.random.rand(512).astype(np.float32).tolist()},
        ]

        result = build_index(str(workspace), chunks, embeddings)
        assert result["success"] is True
        assert result["chunk_count"] == 3
        assert index_exists(str(workspace)) is True

        # Use the first chunk's vector as query; should return itself
        hits = hybrid_search(
            str(workspace),
            query_dense=embeddings[0]["dense_vec"],
            query_text="人工智能 医疗",
            top_k=3,
        )
        assert len(hits) > 0
        assert hits[0]["id"] == "c1"

    def test_search_with_topic_filter(self, workspace: Path):
        chunks = [
            {
                "id": "c1",
                "content": "人工智能在医疗诊断中的应用",
                "file_path": "a.md",
                "topic": "T1",
                "tags": [],
                "section_title": "",
            },
            {
                "id": "c2",
                "content": "深度学习用于图像识别",
                "file_path": "b.md",
                "topic": "T2",
                "tags": [],
                "section_title": "",
            },
        ]
        embeddings = [
            {"dense_vec": ([1.0] + [0.0] * 511)},
            {"dense_vec": ([0.0] * 511 + [1.0])},
        ]
        build_index(str(workspace), chunks, embeddings)

        hits = hybrid_search(
            str(workspace),
            query_dense=embeddings[0]["dense_vec"],
            query_text="医疗 诊断",
            top_k=3,
            topics=["T1"],
        )
        assert len(hits) == 1
        assert hits[0]["id"] == "c1"

    def test_bm25_ready_after_build(self, workspace: Path):
        chunks = [
            {
                "id": "c1",
                "content": "关键词匹配测试内容",
                "file_path": "a.md",
                "topic": "T1",
                "tags": [],
                "section_title": "",
            },
        ]
        embeddings = [{"dense_vec": np.random.rand(512).astype(np.float32).tolist()}]
        build_index(str(workspace), chunks, embeddings)
        assert bm25_index_ready(str(workspace)) is True

    def test_ensure_bm25_rebuilds_when_dir_missing(self, workspace: Path):
        chunks = [
            {
                "id": "c1",
                "content": "重建 BM25 索引测试",
                "file_path": "a.md",
                "topic": "T1",
                "tags": [],
                "section_title": "",
            },
        ]
        embeddings = [{"dense_vec": np.random.rand(512).astype(np.float32).tolist()}]
        build_index(str(workspace), chunks, embeddings)
        ws = str(workspace)

        import shutil

        from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER

        bm25_dir = workspace / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER / "bm25s"
        shutil.rmtree(bm25_dir)
        clear_bm25_cache(ws)

        assert bm25_index_ready(ws) is False
        assert ensure_bm25_index(ws) is True

        hits = hybrid_search(
            ws,
            query_dense=embeddings[0]["dense_vec"],
            query_text="重建 BM25",
            top_k=1,
        )
        assert hits
        assert hits[0].get("bm25_used") is True
        assert hits[0].get("sparse_score", 0) > 0


class TestCollectionCache:
    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "ws"
        ws.mkdir()
        return ws

    def test_get_collection_reuses_cached_handle(self, workspace: Path, monkeypatch: pytest.MonkeyPatch):
        from sidecar.rag.index import _get_collection, build_index, clear_collection_cache

        chunks = [
            {
                "id": "c1",
                "content": "缓存复用测试",
                "file_path": "a.md",
                "topic": "T1",
                "tags": [],
                "section_title": "",
            },
        ]
        embeddings = [{"dense_vec": np.random.rand(512).astype(np.float32).tolist()}]
        build_index(str(workspace), chunks, embeddings)

        real_open = zvec.open
        open_calls: list[str] = []

        def tracking_open(path: str):
            open_calls.append(path)
            return real_open(path)

        monkeypatch.setattr("sidecar.rag.index.zvec.open", tracking_open)
        clear_collection_cache(str(workspace))
        # Re-prime cache without counting the priming open.
        _get_collection(str(workspace))
        open_calls.clear()

        first = _get_collection(str(workspace))
        second = _get_collection(str(workspace))

        assert first is second
        assert open_calls == []

    def test_open_or_create_retries_after_in_process_lock(self, workspace: Path, monkeypatch: pytest.MonkeyPatch):
        from sidecar.rag.index import _open_or_create_collection, build_index

        chunks = [
            {
                "id": "c1",
                "content": "锁重试测试",
                "file_path": "a.md",
                "topic": "T1",
                "tags": [],
                "section_title": "",
            },
        ]
        embeddings = [{"dense_vec": np.random.rand(512).astype(np.float32).tolist()}]
        build_index(str(workspace), chunks, embeddings)

        from sidecar.rag.index import clear_collection_cache

        clear_collection_cache(str(workspace))

        from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER

        path = str(workspace / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER / "zvec_collection")
        real_open = zvec.open
        attempts = {"count": 0}

        def flaky_open(p: str):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError(f"Can't lock read-write collection: {p}/LOCK")
            return real_open(p)

        monkeypatch.setattr("sidecar.rag.index.zvec.open", flaky_open)

        collection = _open_or_create_collection(path)
        assert collection is not None
        assert attempts["count"] == 2
