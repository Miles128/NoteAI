"""RAG index stage helpers used by the ingest pipeline."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from config import config
from config.settings import NOTES_FOLDER
from sidecar.ingest_state import is_cancelled
from utils.logger import logger


def _index_markdown_files(
    workspace: str,
    files: list[Path],
    progress_cb: Callable[[int, int, str], None] | None,
    cancelled: Callable[[], bool] = is_cancelled,
) -> tuple[int, list[str]]:
    from sidecar.rag.index import index_operation

    with index_operation(workspace, blocking=False) as acquired:
        if not acquired:
            raise RuntimeError("RAG 索引正在由另一个任务更新，请稍后重试")
        return _index_markdown_files_locked(workspace, files, progress_cb, cancelled)


def _index_markdown_files_locked(
    workspace: str,
    files: list[Path],
    progress_cb: Callable[[int, int, str], None] | None,
    cancelled: Callable[[], bool],
) -> tuple[int, list[str]]:
    if not config.rag_enabled:
        return 0, []

    from sidecar.rag.chunker import chunk_file
    from sidecar.rag.embedder import encode_documents
    from sidecar.rag.index import count_indexed_chunks, load_manifest, replace_file_chunks
    from sidecar.rag.index_state import file_needs_index, mark_many_indexed

    manifest = load_manifest(workspace)
    expected_chunks = sum(len(entry.get("chunks") or []) for entry in manifest.get("files", {}).values())
    actual_chunks = count_indexed_chunks(workspace, allow_metadata_fallback=False)
    if actual_chunks < 0:
        raise RuntimeError("RAG 索引当前不可访问，请关闭其他 NoteAI 实例后重试")
    repair_all = expected_chunks > 0 and actual_chunks != expected_chunks
    if repair_all:
        logger.warning(
            "[ingest/index] integrity mismatch actual=%s expected=%s; repairing all notes",
            actual_chunks,
            expected_chunks,
        )
        ws_path = Path(workspace)
        files = [
            md
            for md in ws_path.rglob("*.md")
            if not md.name.startswith(".")
            and not any(part.startswith(".") for part in md.relative_to(ws_path).parts[:-1])
            and "wiki" not in md.parts
            and NOTES_FOLDER in md.parts
            and not md.name.endswith("_综述.md")
        ]

    indexed = 0
    indexed_paths: list[str] = []
    total = len(files)
    replacements: dict[str, dict] = {}
    pending_updates: dict[str, float] = {}
    preparation_errors: list[str] = []

    for i, md in enumerate(files):
        if cancelled():
            break
        try:
            rel = str(md.relative_to(workspace))
            mtime = md.stat().st_mtime
            if not repair_all and not file_needs_index(rel, mtime, workspace):
                if progress_cb:
                    progress_cb(i + 1, total, f"跳过未改动 ({i + 1}/{total}): {md.name}")
                continue
            if progress_cb:
                progress_cb(i + 1, total, f"索引 ({i + 1}/{total}): {md.name}")
            text = md.read_text(encoding="utf-8")
            chunks = chunk_file(rel, text)
            if not chunks:
                replacements[rel] = {
                    "chunks": [],
                    "embeddings": [],
                    "mtime": mtime,
                    "size": md.stat().st_size,
                }
                pending_updates[rel] = mtime
                continue
            embeddings = encode_documents([c["content"] for c in chunks])
            replacements[rel] = {
                "chunks": chunks,
                "embeddings": embeddings,
                "mtime": mtime,
                "size": md.stat().st_size,
            }
            pending_updates[rel] = mtime
        except Exception as e:
            logger.warning("[ingest/index] failed to prepare %s: %s", md, e)
            preparation_errors.append(f"{md.name}: {e}")
            continue

    if preparation_errors:
        raise RuntimeError(f"索引准备失败 {len(preparation_errors)} 篇: {'; '.join(preparation_errors[:3])}")

    # Do not mutate the index after cancellation. Prepared embeddings can be
    # safely discarded and the unchanged state will cause a retry next run.
    if cancelled():
        return 0, []

    if pending_updates:
        replace_file_chunks(workspace, replacements)
        mark_many_indexed(pending_updates, workspace)
        indexed = len(pending_updates)
        indexed_paths = list(pending_updates)

    return indexed, indexed_paths


def _purge_deleted_index_files(workspace: str) -> list[str]:
    """Remove chunks and state entries for Notes files deleted from disk."""
    if not config.rag_enabled:
        return []

    from sidecar.rag.index import delete_files_batched
    from sidecar.rag.index_state import load_state, remove_indexed

    ws = Path(workspace)
    stale_paths = [rel for rel in load_state(workspace) if not (ws / rel).is_file()]
    if stale_paths:
        # 批量删除：单次 writer lock + 末尾一次 BM25 重建（原实现逐文件全量重建）
        delete_files_batched(workspace, stale_paths)
        remove_indexed(stale_paths, workspace)
    return stale_paths
