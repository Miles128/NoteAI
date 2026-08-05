"""RAG pipeline package.

The RAG stack (zvec, bm25s, fastembed, FlagEmbedding) is an optional feature.
If dependencies are missing, callers can use ``utils.package_manager.ensure_feature("rag")``
to install them on demand.
"""

from __future__ import annotations

_RAG_AVAILABLE: bool | None = None
_RAG_IMPORT_ERROR: str = ""


def _check_rag_available() -> tuple[bool, str]:
    """Lazily check whether the RAG optional dependencies are importable."""
    global _RAG_AVAILABLE, _RAG_IMPORT_ERROR
    if _RAG_AVAILABLE is not None:
        return _RAG_AVAILABLE, _RAG_IMPORT_ERROR
    missing = []
    for mod_name in ("zvec", "bm25s", "fastembed", "numpy"):
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(mod_name)
    if missing:
        _RAG_AVAILABLE = False
        _RAG_IMPORT_ERROR = f"missing RAG dependencies: {', '.join(missing)}"
    else:
        _RAG_AVAILABLE = True
        _RAG_IMPORT_ERROR = ""
    return _RAG_AVAILABLE, _RAG_IMPORT_ERROR


# Backward-compatible module-level attributes (evaluated lazily via __getattr__).
def __getattr__(name: str):
    if name == "RAG_AVAILABLE":
        avail, _ = _check_rag_available()
        return avail
    if name == "RAG_IMPORT_ERROR":
        _, err = _check_rag_available()
        return err
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
