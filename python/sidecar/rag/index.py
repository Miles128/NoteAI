"""Lightweight local RAG index using zvec + BM25s.

Public API stays on this module so callers keep ``from sidecar.rag.index import ...``.
Implementation is split across ``index_core`` / ``index_crud`` / ``index_bm25`` / ``index_query``.
Private helpers are resolved via ``__getattr__`` for test and internal callers.
"""

from __future__ import annotations

from sidecar.rag.index_bm25 import (
    bm25_index_ready,
    ensure_bm25_index,
    rebuild_search_indices,
)
from sidecar.rag.index_core import (
    clear_bm25_cache,
    clear_collection_cache,
    filter_usable_chunks,
    index_exists,
    index_operation,
    is_usable_chunk,
    load_manifest,
    manifest_path,
    save_manifest,
)
from sidecar.rag.index_crud import (
    add_chunks,
    build_index,
    delete_by_file,
    delete_files_batched,
    replace_file_chunks,
)
from sidecar.rag.index_query import (
    count_indexed_chunks,
    fetch_chunks_by_file,
    hybrid_search,
)

__all__ = [
    "add_chunks",
    "bm25_index_ready",
    "build_index",
    "clear_bm25_cache",
    "clear_collection_cache",
    "count_indexed_chunks",
    "delete_by_file",
    "delete_files_batched",
    "ensure_bm25_index",
    "fetch_chunks_by_file",
    "filter_usable_chunks",
    "hybrid_search",
    "index_exists",
    "index_operation",
    "is_usable_chunk",
    "load_manifest",
    "manifest_path",
    "rebuild_search_indices",
    "replace_file_chunks",
    "save_manifest",
]


def __getattr__(name: str):
    from sidecar.rag import index_bm25, index_core, index_crud, index_query

    for mod in (index_core, index_crud, index_bm25, index_query):
        if hasattr(mod, name):
            value = getattr(mod, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
