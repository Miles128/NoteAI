"""RAG index core: paths, collection cache, metadata, manifest, doc conversion."""

from __future__ import annotations

import copy
import gc
import json
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import zvec

from config.settings import RAG_INDEX_FOLDER, WORKSPACE_APP_FOLDER
from utils.error_handler import log_exception
from utils.logger import logger

_COLLECTION_NAME = "noteai_chunks"
_DENSE_DIM = 512
_DENSE_METRIC = zvec.MetricType.COSINE
_INDEX_BATCH_SIZE = 128
_FETCH_BATCH_SIZE = 256
_INDEX_VERSION = 2

_lock = threading.Lock()

# Cache opened collections per workspace to avoid repeated zvec.open() cost
# (zvec.open reloads the mmindex every time, which is expensive for large indices).
_COLLECTION_CACHE: dict[str, zvec.Collection] = {}
_COLLECTION_CACHE_LOCK = threading.Lock()
_COLLECTION_IO_LOCK = threading.RLock()

# Serialize complete indexing operations per workspace. zvec permits concurrent
# readers, but writes are single-process exclusive; callers must not prepare and
# commit two independent index generations at the same time.
_INDEX_OPERATION_LOCKS: dict[str, threading.Lock] = {}
_INDEX_OPERATION_LOCKS_GUARD = threading.Lock()

# In-memory BM25 retriever cache (bm25s.load is costly on every query).
_BM25_CACHE: dict[str, tuple[Any, list[dict]]] = {}
_BM25_CACHE_LOCK = threading.Lock()

# manifest/metadata 的内存缓存：(stat_key, data)。读侧按 stat 键失效，
# 写侧（_write_manifest/_save_metadata）显式清除——避免每轮 RAG 查询
# 重复读盘解析大 JSON（万级 chunk 时数百 KB~MB）。
_MANIFEST_CACHE: dict[str, tuple[tuple[float, int] | None, dict]] = {}
_MANIFEST_CACHE_LOCK = threading.Lock()
_METADATA_CACHE: dict[str, tuple[tuple[float, int] | None, dict[str, Any]]] = {}
_METADATA_CACHE_LOCK = threading.Lock()


def _normalize_workspace(workspace: str) -> str:
    return str(Path(workspace).expanduser().resolve())


@contextmanager
def index_operation(workspace: str, *, blocking: bool = False):
    """Acquire the workspace-wide index writer lease."""
    ws = _normalize_workspace(workspace)
    with _INDEX_OPERATION_LOCKS_GUARD:
        lock = _INDEX_OPERATION_LOCKS.setdefault(ws, threading.Lock())
    acquired = lock.acquire(blocking=blocking)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


def _rag_index_dir(workspace: str) -> Path:
    return Path(_normalize_workspace(workspace)) / WORKSPACE_APP_FOLDER / RAG_INDEX_FOLDER


def _collection_path(workspace: str) -> Path:
    p = _rag_index_dir(workspace) / "zvec_collection"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _bm25s_dir(workspace: str) -> Path:
    p = _rag_index_dir(workspace) / "bm25s"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _metadata_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "metadata.json"


def _manifest_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "manifest.json"


def _stat_key(path: Path) -> tuple[float, int] | None:
    try:
        st = path.stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def _read_manifest(workspace: str) -> dict:
    """Read the index manifest, returning a default if missing or invalid."""
    path = _manifest_path(workspace)
    stat_key = _stat_key(path)
    with _MANIFEST_CACHE_LOCK:
        cached = _MANIFEST_CACHE.get(workspace)
        if cached is not None and cached[0] == stat_key:
            return cached[1]
    data: dict = {}
    if stat_key is not None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    with _MANIFEST_CACHE_LOCK:
        _MANIFEST_CACHE[workspace] = (stat_key, data)
    return data


def _write_manifest(workspace: str, data: dict) -> None:
    """Atomically write the index manifest."""

    path = _manifest_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        with _MANIFEST_CACHE_LOCK:
            _MANIFEST_CACHE.pop(workspace, None)
    except OSError as e:
        log_exception("[rag/index] failed to write manifest", e, level="warning", logger=logger)


def _manifest_version_ok(workspace: str) -> bool:
    """Check whether the on-disk index version matches the current schema version."""
    manifest = _read_manifest(workspace)
    return manifest.get("version") == _INDEX_VERSION


def _bump_manifest_version(workspace: str) -> None:
    manifest = _read_manifest(workspace)
    manifest["version"] = _INDEX_VERSION
    manifest["schema_version"] = _INDEX_VERSION
    import time as _time

    manifest["last_rebuilt"] = _time.time()
    _write_manifest(workspace, manifest)


def _build_schema() -> zvec.CollectionSchema:
    return zvec.CollectionSchema(
        name=_COLLECTION_NAME,
        fields=[
            zvec.FieldSchema("content", zvec.DataType.STRING),
            zvec.FieldSchema("file_path", zvec.DataType.STRING, index_param=zvec.InvertIndexParam()),
            zvec.FieldSchema("topic", zvec.DataType.STRING, index_param=zvec.InvertIndexParam()),
            zvec.FieldSchema("tags_json", zvec.DataType.STRING),
            zvec.FieldSchema("section_title", zvec.DataType.STRING),
        ],
        vectors=[
            zvec.VectorSchema(
                "dense",
                zvec.DataType.VECTOR_FP32,
                dimension=_DENSE_DIM,
                index_param=zvec.HnswIndexParam(metric_type=_DENSE_METRIC),
            ),
        ],
    )


def _is_zvec_lock_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "被占用" in str(exc)


def _collection_lock_error(workspace: str | None = None) -> RuntimeError:
    hint = "请稍候重试"
    if workspace:
        try:
            import psutil

            lock_root = _collection_path(workspace)
            for lock_file in lock_root.rglob("LOCK"):
                content = lock_file.read_text().strip() if lock_file.stat().st_size else ""
                if content and content.isdigit() and psutil.pid_exists(int(content)):
                    if int(content) != psutil.Process().pid:
                        hint = "请关闭其他 NoteAI 实例后重试"
                    break
        except Exception:
            pass
    return RuntimeError(f"RAG 索引文件被占用，{hint}")


def _take_cached_collection(workspace: str) -> zvec.Collection | None:
    """Remove a workspace collection handle from cache.

    zvec.Collection.destroy() deletes the on-disk collection; it is not a
    close operation. Releasing the final Python reference closes the native
    handle without erasing user data.
    """
    ws = _normalize_workspace(workspace)
    with _COLLECTION_CACHE_LOCK:
        collection = _COLLECTION_CACHE.pop(ws, None)
    return collection


def _remove_stale_lock(path: str) -> bool:
    """Never unlink RocksDB LOCK files.

    RocksDB lock files are normally zero bytes and their ownership lives in an
    OS file lock, not in file contents. Unlinking one on Unix can bypass an
    active writer's lock by creating a new inode at the same path.
    """
    return False


def _release_collection(workspace: str, *, remove_data: bool = False) -> None:
    """Release the cached zvec handle and optionally wipe collection data."""
    ws = _normalize_workspace(workspace)
    collection = _take_cached_collection(ws)
    collection = None
    gc.collect()
    path = _collection_path(ws)
    if remove_data and path.exists():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        _remove_stale_lock(str(path))
    gc.collect()


def _open_or_create_collection(path: str, workspace: str | None = None) -> zvec.Collection:
    """Open an existing collection, retrying after GC / stale-lock cleanup / force release."""
    ws = _normalize_workspace(workspace) if workspace else None
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            return zvec.open(path)
        except Exception as e:
            last_err = e
            if not _is_zvec_lock_error(e) or not Path(path).exists():
                break
            gc.collect()
            if attempt == 0:
                continue
            if ws is not None:
                _release_collection(ws)
                gc.collect()
                time.sleep(0.05 * (attempt + 1))
                continue
            break
    if last_err and _is_zvec_lock_error(last_err) and Path(path).exists():
        raise _collection_lock_error(ws) from last_err
    log_exception(
        "[rag/index] failed to open existing collection, creating new", last_err, level="warning", logger=logger
    )
    return zvec.create_and_open(path, _build_schema())


def _get_collection(workspace: str) -> zvec.Collection:
    ws = _normalize_workspace(workspace)
    with _COLLECTION_IO_LOCK:
        with _COLLECTION_CACHE_LOCK:
            cached = _COLLECTION_CACHE.get(ws)
            if cached is not None and _manifest_version_ok(ws):
                return cached

        destroy = not _manifest_version_ok(ws)
        _take_cached_collection(ws)

        path = str(_collection_path(ws))
        if destroy and Path(path).exists():
            logger.info("[RAG] index version mismatch, rebuilding collection")
            shutil.rmtree(path, ignore_errors=True)
            bm25s = _bm25s_dir(ws)
            if bm25s.exists():
                shutil.rmtree(bm25s, ignore_errors=True)
            _remove_stale_lock(path)
        elif not destroy:
            gc.collect()

        collection = _open_or_create_collection(path, ws)

        with _COLLECTION_CACHE_LOCK:
            cached = _COLLECTION_CACHE.get(ws)
            if cached is not None and _manifest_version_ok(ws):
                return cached
            _COLLECTION_CACHE[ws] = collection
            return collection


def clear_bm25_cache(workspace: str | None = None) -> None:
    """Drop cached BM25 retriever(s)."""
    with _BM25_CACHE_LOCK:
        if workspace is None:
            _BM25_CACHE.clear()
        else:
            _BM25_CACHE.pop(workspace, None)


def clear_collection_cache(workspace: str | None = None) -> None:
    """Drop cached collection handles without deleting on-disk data."""
    with _COLLECTION_IO_LOCK:
        with _COLLECTION_CACHE_LOCK:
            workspaces = (
                [_normalize_workspace(ws) for ws in _COLLECTION_CACHE]
                if workspace is None
                else [_normalize_workspace(workspace)]
            )
        for ws in workspaces:
            collection = _take_cached_collection(ws)
            collection = None
        with _COLLECTION_CACHE_LOCK:
            if workspace is None:
                _COLLECTION_CACHE.clear()
            else:
                _COLLECTION_CACHE.pop(_normalize_workspace(workspace), None)
        gc.collect()
        clear_bm25_cache(workspace)


def _escape_filter_value(value: str) -> str:
    """Escape a string for use in a zvec filter expression."""
    text = str(value)
    if "\x00" in text:
        raise ValueError("filter value contains null byte")
    if any(ord(ch) < 32 for ch in text):
        raise ValueError("filter value contains control characters")
    return "'" + text.replace("'", "''") + "'"


def is_usable_chunk(result: dict) -> bool:
    content = (result.get("content") or "").strip()
    return bool(content)


def filter_usable_chunks(results: list[dict]) -> list[dict]:
    return [r for r in results if is_usable_chunk(r)]


def index_exists(workspace: str) -> bool:
    return _collection_path(workspace).exists() and _metadata_path(workspace).exists()


def _empty_metadata() -> dict[str, Any]:
    return {"topics": {}, "tags": {}, "files": {}, "version": 2}


def _load_metadata(workspace: str) -> dict[str, Any]:
    path = _metadata_path(workspace)
    stat_key = _stat_key(path)
    with _METADATA_CACHE_LOCK:
        cached = _METADATA_CACHE.get(workspace)
        if cached is not None and cached[0] == stat_key:
            # deepcopy 保护：读侧可能后续 mutate（写路径），缓存本体须保持干净
            return copy.deepcopy(cached[1])
    data = _empty_metadata()
    if stat_key is not None:
        try:
            with path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    loaded.setdefault("topics", {})
                    loaded.setdefault("tags", {})
                    loaded.setdefault("files", {})
                    data = loaded
        except Exception as e:
            log_exception("[rag/index] failed to load metadata", e, level="warning", logger=logger)
    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE[workspace] = (stat_key, copy.deepcopy(data))
    return data


def _save_metadata(workspace: str, metadata: dict[str, Any]) -> None:
    path = _metadata_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False)
    tmp.replace(path)
    with _METADATA_CACHE_LOCK:
        _METADATA_CACHE.pop(workspace, None)


def _update_metadata_index(metadata: dict[str, Any], chunk: dict, mode: str = "add") -> None:
    chunk_id = chunk["id"]
    topic = chunk.get("topic") or ""
    tags = chunk.get("tags") or []
    file_path = chunk.get("file_path") or ""

    def _mutate(key: str, value: str) -> None:
        if not value:
            return
        bucket = metadata.setdefault(key, {})
        ids = set(bucket.get(value, []))
        if mode == "add":
            ids.add(chunk_id)
        else:
            ids.discard(chunk_id)
        if ids:
            bucket[value] = sorted(ids)
        else:
            bucket.pop(value, None)

    _mutate("topics", topic)
    _mutate("files", file_path)
    for tag in tags:
        _mutate("tags", tag)


def _chunk_to_doc(chunk: dict, embedding: dict) -> zvec.Doc:
    cid = chunk.get("id", "")
    content = (chunk.get("content") or "")[:8192]
    file_path = (chunk.get("file_path") or "")[:512]
    topic = (chunk.get("topic") or "")[:256]
    tags = chunk.get("tags") or []
    section_title = (chunk.get("section_title") or "")[:256]
    vec = embedding.get("dense_vec") or [0.0] * _DENSE_DIM

    return zvec.Doc(
        id=cid,
        vectors={"dense": vec},
        fields={
            "content": content,
            "file_path": file_path,
            "topic": topic,
            "tags_json": json.dumps(tags, ensure_ascii=False),
            "section_title": section_title,
        },
    )


def _tags_from_fields(fields: dict) -> list[str]:
    try:
        return json.loads(fields.get("tags_json") or "[]")
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        log_exception("[rag/index] failed to parse tags_json", e, level="debug", logger=logger)
        return []


def _doc_to_result(doc: zvec.Doc, score: float | None = None) -> dict:
    fields = doc.fields or {}
    dense_vec = None
    vectors = getattr(doc, "vectors", None)
    if isinstance(vectors, dict) and isinstance(vectors.get("dense"), list):
        dense_vec = vectors["dense"]
    return {
        "id": doc.id,
        "content": fields.get("content", ""),
        "file_path": fields.get("file_path", ""),
        "topic": fields.get("topic", ""),
        "tags": _tags_from_fields(fields),
        "section_title": fields.get("section_title", ""),
        "dense_vec": dense_vec,
        "dense_score": score if score is not None else 0.0,
        "sparse_score": 0.0,
        "score": score if score is not None else 0.0,
    }


def _write_docs_batched(collection: zvec.Collection, docs: list[zvec.Doc], *, insert: bool = False) -> None:
    """Write within zvec's maximum request size."""
    operation = collection.insert if insert else collection.upsert
    for offset in range(0, len(docs), _INDEX_BATCH_SIZE):
        operation(docs[offset : offset + _INDEX_BATCH_SIZE])


def _delete_ids_batched(collection: zvec.Collection, ids: list[str]) -> None:
    for offset in range(0, len(ids), _INDEX_BATCH_SIZE):
        collection.delete(ids[offset : offset + _INDEX_BATCH_SIZE])


def _chunk_ids_from_metadata(workspace: str) -> list[str]:
    """Collect all chunk ids tracked in metadata inverted indices."""
    metadata = _load_metadata(workspace)
    ids: set[str] = set()
    for bucket in (metadata.get("topics", {}), metadata.get("tags", {}), metadata.get("files", {})):
        for id_list in bucket.values():
            ids.update(id_list)
    return sorted(ids)


def manifest_path(workspace: str) -> Path:
    return _rag_index_dir(workspace) / "file_manifest.json"


def load_manifest(workspace: str) -> dict[str, Any]:
    path = manifest_path(workspace)
    if not path.exists():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "files" in data:
            data.setdefault("version", 1)
            return data
    except Exception as e:
        log_exception("[rag/index] failed to load file manifest", e, level="warning", logger=logger)
    return {"version": 1, "files": {}}


def save_manifest(workspace: str, manifest: dict[str, Any]) -> None:
    path = manifest_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False)
    tmp.replace(path)
