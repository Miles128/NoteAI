"""Disk usage and cleanup for local RAG models and workspace indexes.

Does not touch project ``.venv`` or user notes. Safe roots are
``SYSTEM_APP_DATA_DIR`` and the current workspace's index folders.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from config.constants import RAG_INDEX_FOLDER, SYSTEM_APP_DATA_DIR, WORKSPACE_APP_FOLDER
from utils.logger import logger

VALID_TARGETS = frozenset({"hf_hub", "fastembed", "index", "stale_fastembed"})

_HF_DIRNAME = "hf_hub"
_FASTEMBED_DIRNAME = "fastembed_cache"


def hf_hub_dir() -> Path:
    return SYSTEM_APP_DATA_DIR / _HF_DIRNAME


def fastembed_cache_dir() -> Path:
    return SYSTEM_APP_DATA_DIR / _FASTEMBED_DIRNAME


def dir_size_bytes(path: Path) -> int:
    """Apparent unique-file size. Dedupes hard links (HF hub blobs/snapshots)."""
    if not path.exists():
        return 0
    seen: set[tuple[int, int]] = set()
    total = 0
    candidates = [path] if path.is_file() else path.rglob("*")
    for child in candidates:
        if not child.is_file():
            continue
        try:
            st = child.stat()
        except OSError:
            continue
        key = (st.st_dev, st.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += st.st_size
    return total


def _resolved_workspace(workspace: str | None) -> Path | None:
    if not workspace or not str(workspace).strip():
        return None
    try:
        path = Path(workspace).expanduser().resolve()
    except OSError:
        return None
    if path == path.anchor or path == Path(path.anchor):
        return None
    return path


def _index_dirs(workspace: str | None) -> list[Path]:
    ws = _resolved_workspace(workspace)
    if ws is None:
        return []
    return [
        ws / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER,
        ws / RAG_INDEX_FOLDER,
        ws / f".{RAG_INDEX_FOLDER}",
    ]


def stale_fastembed_dirs(root: Path | None = None) -> list[Path]:
    """Old flattened FastEmbed folders (``fast-*``), not the current HF hub layout."""
    cache = root or fastembed_cache_dir()
    if not cache.is_dir():
        return []
    stale: list[Path] = []
    for child in cache.iterdir():
        if child.is_dir() and child.name.startswith("fast-"):
            stale.append(child)
    return stale


def purge_stale_fastembed(root: Path | None = None) -> dict[str, Any]:
    cache = root or fastembed_cache_dir()
    freed = 0
    removed: list[str] = []
    for path in stale_fastembed_dirs(cache):
        size = dir_size_bytes(path)
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            freed += size
            removed.append(str(path))
            logger.info("[storage] purged stale FastEmbed dir %s (%s bytes)", path, size)
    tmp = cache / "tmp"
    if tmp.is_dir():
        shutil.rmtree(tmp, ignore_errors=True)
    return {"success": True, "freed_bytes": freed, "removed": removed}


def get_storage_usage(workspace: str | None = None, *, purge_stale: bool = True) -> dict[str, Any]:
    purged = purge_stale_fastembed() if purge_stale else {"freed_bytes": 0, "removed": []}
    hf = hf_hub_dir()
    fe = fastembed_cache_dir()
    leftover_stale = sum(dir_size_bytes(p) for p in stale_fastembed_dirs(fe))
    index_paths = _index_dirs(workspace)
    index_bytes = sum(dir_size_bytes(p) for p in index_paths)
    hf_bytes = dir_size_bytes(hf)
    fe_bytes = dir_size_bytes(fe)
    items: list[dict[str, Any]] = [
        {
            "id": "hf_hub",
            "bytes": hf_bytes,
            "path": str(hf),
        },
        {
            "id": "fastembed",
            "bytes": fe_bytes,
            "path": str(fe),
            "stale_bytes": leftover_stale,
        },
        {
            "id": "index",
            "bytes": index_bytes,
            "path": str(index_paths[0]) if index_paths else "",
        },
    ]
    freed_raw = purged.get("freed_bytes")
    purged_stale_bytes = int(freed_raw) if isinstance(freed_raw, (int, float)) else 0
    return {
        "success": True,
        "items": items,
        "total_bytes": hf_bytes + fe_bytes + index_bytes,
        "purged_stale_bytes": purged_stale_bytes,
    }


def _allowed_roots(workspace: str | None) -> list[Path]:
    roots = [SYSTEM_APP_DATA_DIR]
    ws = _resolved_workspace(workspace)
    if ws is not None:
        roots.append(ws)
    return roots


def _is_safe_to_delete(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def _wipe_dir(path: Path, roots: list[Path]) -> int:
    if not path.exists():
        return 0
    if not _is_safe_to_delete(path, roots):
        logger.warning("[storage] refused to delete unsafe path %s", path)
        return 0
    size = dir_size_bytes(path)
    if path.is_file():
        path.unlink(missing_ok=True)
        return size
    shutil.rmtree(path, ignore_errors=True)
    if path.exists():
        logger.warning("[storage] failed to remove %s", path)
        return 0
    return size


def _release_runtime_handles(workspace: str | None, targets: set[str]) -> None:
    if "index" in targets or "hf_hub" in targets or "fastembed" in targets:
        try:
            from sidecar.rag.index import clear_collection_cache

            clear_collection_cache(workspace)
        except Exception as e:
            logger.debug("[storage] skip collection cache release: %s", e)
    if "fastembed" in targets:
        try:
            from sidecar.rag.embedder import reset_dense_model

            reset_dense_model()
        except Exception as e:
            logger.debug("[storage] skip dense model reset: %s", e)
    if "hf_hub" in targets or "fastembed" in targets:
        try:
            from sidecar.rag.reranker import reset_reranker

            reset_reranker()
        except Exception as e:
            logger.debug("[storage] skip reranker reset: %s", e)
        try:
            from sidecar.rag.retriever import clear_query_cache

            clear_query_cache()
        except Exception as e:
            logger.debug("[storage] skip query cache clear: %s", e)


def clear_storage(targets: list[str] | None, workspace: str | None = None) -> dict[str, Any]:
    raw = [str(t).strip() for t in (targets or []) if str(t).strip()]
    unknown = [t for t in raw if t not in VALID_TARGETS]
    if unknown:
        return {"success": False, "message": f"未知清理目标: {', '.join(unknown)}"}
    chosen = set(raw)
    if not chosen:
        return {"success": False, "message": "未指定清理目标"}

    roots = _allowed_roots(workspace)
    _release_runtime_handles(workspace, chosen)
    freed = 0
    cleared: list[str] = []

    if "stale_fastembed" in chosen:
        result = purge_stale_fastembed()
        freed += int(result.get("freed_bytes") or 0)
        if result.get("removed"):
            cleared.append("stale_fastembed")

    if "hf_hub" in chosen:
        path = hf_hub_dir()
        freed += _wipe_dir(path, roots)
        path.mkdir(parents=True, exist_ok=True)
        cleared.append("hf_hub")

    if "fastembed" in chosen:
        path = fastembed_cache_dir()
        freed += _wipe_dir(path, roots)
        path.mkdir(parents=True, exist_ok=True)
        cleared.append("fastembed")

    if "index" in chosen:
        if _resolved_workspace(workspace) is None:
            return {"success": False, "message": "未设置工作区，无法清理索引"}
        for path in _index_dirs(workspace):
            if path.exists():
                freed += _wipe_dir(path, roots)
        cleared.append("index")

    usage = get_storage_usage(workspace, purge_stale=False)
    return {
        "success": True,
        "cleared": cleared,
        "freed_bytes": freed,
        "items": usage["items"],
        "total_bytes": usage["total_bytes"],
    }
