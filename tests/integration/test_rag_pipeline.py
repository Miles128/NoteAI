"""
Integration tests for RAG pipeline: chunker → embedder → index → retriever.

Requires project dependencies (see pyproject.toml). Run: pytest tests/integration/
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from config import config


def _has_milvus_lite() -> bool:
    try:
        import milvus_lite  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    d = tmp_path / "ws"
    d.mkdir()
    (d / "Notes").mkdir()
    (d / "wiki").mkdir(parents=True, exist_ok=True)
    config.workspace_path = str(d)
    return d


class TestChunker:
    """Test the RAG chunking pipeline."""

    def test_chunk_file_with_frontmatter(self) -> None:
        from sidecar.rag.chunker import chunk_file

        content = "---\ntopic: AI > LLM\ntags:\n  - RAG\n---\n\n## Section 1\n\nBody text here.\n\n## Section 2\n\nMore content.\n"
        chunks = chunk_file("Notes/test.md", content)

        assert len(chunks) >= 1
        assert all("file_path" in c for c in chunks)
        assert all("content" in c for c in chunks)

    def test_chunk_file_without_frontmatter(self) -> None:
        from sidecar.rag.chunker import chunk_file

        content = "## Heading\n\nSome content here.\n"
        chunks = chunk_file("Notes/test.md", content)

        assert len(chunks) >= 1
        assert chunks[0]["file_path"] == "Notes/test.md"

    def test_chunk_id_is_deterministic(self) -> None:
        from sidecar.rag.chunker import _make_chunk

        chunk1 = _make_chunk("content", "path", "topic", [], "section")
        chunk2 = _make_chunk("content", "path", "topic", [], "section")

        assert chunk1["id"] == chunk2["id"]

    def test_chunk_id_varies_by_content(self) -> None:
        from sidecar.rag.chunker import _make_chunk

        chunk1 = _make_chunk("content A", "path", "topic", [], "section")
        chunk2 = _make_chunk("content B", "path", "topic", [], "section")

        assert chunk1["id"] != chunk2["id"]

    def test_content_with_multiple_headings_creates_multiple_chunks(self) -> None:
        from sidecar.rag.chunker import chunk_file

        content = "## Section 1\n\nContent for section 1.\n\n## Section 2\n\nContent for section 2.\n\n## Section 3\n\nContent for section 3.\n"
        chunks = chunk_file("Notes/multi.md", content)

        assert len(chunks) >= 3

    def test_empty_content_returns_empty(self) -> None:
        from sidecar.rag.chunker import chunk_file

        chunks = chunk_file("Notes/empty.md", "")
        assert chunks == []

    def test_frontmatter_metadata_preserved(self) -> None:
        from sidecar.rag.chunker import chunk_file

        content = "---\ntopic: AI\ntags:\n  - test\n---\n\n## Section\n\nBody.\n"
        chunks = chunk_file("Notes/test.md", content)

        assert chunks[0]["topic"] == "AI"
        assert "test" in chunks[0]["tags"]


class TestIndex:
    """Test Milvus index operations."""

    @pytest.mark.skipif(not _has_milvus_lite(), reason="milvus-lite not installed")
    def test_index_exists_returns_false_for_empty_workspace(self, workspace: Path) -> None:
        from sidecar.rag.index import index_exists

        assert index_exists(str(workspace)) is False

    @pytest.mark.skipif(not _has_milvus_lite(), reason="milvus-lite not installed")
    def test_build_index(self, workspace: Path) -> None:
        from sidecar.rag.index import build_index, index_exists

        chunks = [
            {
                "id": "chunk_1",
                "content": "AI is transforming the world",
                "file_path": "Notes/test.md",
                "topic": "AI",
                "tags": ["test"],
                "section_title": "Introduction",
            },
        ]

        embeddings = [
            {"dense_vec": [0.1] * 512, "id": "chunk_1"},
        ]

        result = build_index(str(workspace), chunks, embeddings)
        assert result.get("success") is True
        assert index_exists(str(workspace)) is True

    @pytest.mark.skipif(not _has_milvus_lite(), reason="milvus-lite not installed")
    def test_delete_by_file(self, workspace: Path) -> None:
        from sidecar.rag.index import build_index, delete_by_file, index_exists

        chunks = [
            {
                "id": "chunk_a",
                "content": "Content A",
                "file_path": "Notes/a.md",
                "topic": "AI",
                "tags": [],
                "section_title": None,
            },
            {
                "id": "chunk_b",
                "content": "Content B",
                "file_path": "Notes/b.md",
                "topic": "AI",
                "tags": [],
                "section_title": None,
            },
        ]
        embeddings = [
            {"dense_vec": [0.1] * 512, "id": "chunk_a"},
            {"dense_vec": [0.2] * 512, "id": "chunk_b"},
        ]

        build_index(str(workspace), chunks, embeddings)
        assert index_exists(str(workspace)) is True

        delete_by_file(str(workspace), "Notes/a.md")

        assert index_exists(str(workspace)) is True


class TestContextExpand:
    """Test context expansion for retrieval."""

    def test_confirmed_neighbor_paths_empty(self, workspace: Path) -> None:
        from sidecar.rag.context_expand import _confirmed_neighbor_paths

        paths = _confirmed_neighbor_paths("Notes/test.md")
        assert isinstance(paths, list)

    def test_read_file_excerpt(self, workspace: Path) -> None:
        from sidecar.rag.context_expand import _read_file_excerpt

        note = workspace / "Notes" / "test.md"
        note.write_text("# Title\n\nBody content here.\n", encoding="utf-8")

        excerpt = _read_file_excerpt(str(workspace), "Notes/test.md", 100)
        assert "Body content" in excerpt

    def test_read_file_excerpt_missing_file(self, workspace: Path) -> None:
        from sidecar.rag.context_expand import _read_file_excerpt

        excerpt = _read_file_excerpt(str(workspace), "Notes/missing.md", 100)
        assert excerpt == ""


class TestRagHandler:
    """Test RAG handler RPC contracts."""

    def test_init_rag_index_disabled(self, workspace: Path) -> None:
        from sidecar.handlers.rag_handler import RagHandler

        original_rag_enabled = config.rag_enabled
        config.rag_enabled = False

        try:
            srv = SimpleNamespace(
                _ctx=SimpleNamespace(config=config, logger=None),
                _running_tasks=set(),
                _running_tasks_lock=__import__("threading").Lock(),
            )
            handler = RagHandler(srv)

            result = handler._init_rag_index({})
            assert result.get("success") is False
            assert "未启用" in result.get("message", "")
        finally:
            config.rag_enabled = original_rag_enabled


class TestEmbedder:
    """Test embedding generation."""

    def test_encode_query_returns_dense_vec(self) -> None:
        from sidecar.rag.embedder import encode_query

        try:
            result = encode_query("test query")
        except Exception as e:
            if "Could not load model" in str(e) or "offline" in str(e).lower():
                pytest.skip(f"Embedding model unavailable: {e}")
            raise
        assert "dense_vec" in result
        assert len(result["dense_vec"]) == 512

    def test_encode_query_empty_returns_empty(self) -> None:
        from sidecar.rag.embedder import encode_query

        result = encode_query("")
        assert result == {} or result.get("dense_vec") is None
