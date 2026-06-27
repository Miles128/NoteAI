"""RAG pipeline package.

The RAG stack (zvec, bm25s, fastembed, FlagEmbedding) is an optional feature.
If dependencies are missing, callers can use ``utils.package_manager.ensure_feature("rag")``
to install them on demand.
"""

from __future__ import annotations


def _try_import_rag() -> tuple[bool, str]:
    """Check whether the RAG optional dependencies are importable."""
    missing = []
    for mod_name in ("zvec", "bm25s", "fastembed", "numpy"):
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(mod_name)
    if missing:
        return False, f"missing RAG dependencies: {', '.join(missing)}"
    return True, ""


RAG_AVAILABLE, RAG_IMPORT_ERROR = _try_import_rag()
