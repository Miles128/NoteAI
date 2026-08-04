"""Workspace backup / export / restore and index health checks.

Local-reliability layer (PRD P1): every derived index (RAG collection, BM25,
semantic store, graph) is rebuildable, so backups deliberately exclude them.
Restore is path-traversal-safe and moves overwritten folders into
``.trash/restore-<ts>/`` so the previous state can be rolled back manually.
"""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from config.settings import SYSTEM_APP_DATA_DIR

# Rebuildable or disposable content excluded from backups by default.
_DERIVED_DIR_NAMES = {
    ".rag",
    "zvec",
    "bm25",
    ".semantic",
    ".graph",
    ".cache",
    ".trash",
    "__pycache__",
    "node_modules",
    ".git",
}
_SKIP_FILE_NAMES = {".DS_Store", "Thumbs.db"}

# Top-level folders / files that form the user-owned workspace content.
_CONTENT_FOLDERS = ("Notes", "wiki", "Raw", "RawArchive")
_CONTENT_FILES = (".links.json", "tags.md", "topics.md")
_MANIFEST_NAME = "manifest.json"

_BACKUP_SUBDIR = "backups"


def default_backup_dir() -> Path:
    """Where backups live when no target directory is requested."""
    return SYSTEM_APP_DATA_DIR / _BACKUP_SUBDIR


def _skip_dir(rel_parts: tuple[str, ...]) -> bool:
    return any(part in _DERIVED_DIR_NAMES for part in rel_parts)


def _skip_file(name: str) -> bool:
    return name in _SKIP_FILE_NAMES or name.startswith(".")


def collect_workspace_files(
    workspace: str,
    *,
    include_derived: bool = False,
    export_only: bool = False,
) -> tuple[list[tuple[Path, str]], int]:
    """Collect (absolute, relative-posix) files to archive.

    ``export_only`` keeps just Notes/ + tags.md (pure user content).
    Skipped files are counted but not included.
    """
    root = Path(workspace)
    files: list[tuple[Path, str]] = []
    skipped = 0
    folders = ("Notes",) if export_only else _CONTENT_FOLDERS
    for folder in folders:
        base = root / folder
        if not base.is_dir():
            continue
        for file_path in sorted(base.rglob("*")):
            rel = file_path.relative_to(root)
            parts = rel.parts
            if file_path.is_dir():
                continue
            if _skip_file(file_path.name):
                skipped += 1
                continue
            if not include_derived and _skip_dir(parts):
                skipped += 1
                continue
            files.append((file_path, rel.as_posix()))
    for name in _CONTENT_FILES:
        if export_only and name != "tags.md":
            continue
        file_path = root / name
        if file_path.is_file():
            files.append((file_path, name))
    if not export_only and not include_derived:
        for dotfile in root.glob(".*"):
            if dotfile.is_file() and dotfile.name not in {".gitignore", ".links.json"}:
                skipped += 1
    return files, skipped


def _write_zip(zip_path: Path, workspace: str, files: list[tuple[Path, str]]) -> dict:
    manifest: dict[str, Any] = {
        "app": "NoteAI",
        "kind": "workspace-backup",
        "created_at": datetime.now().astimezone().isoformat(),
        "workspace_name": Path(workspace).name,
        "file_count": len(files),
        "version": 1,
    }
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr(_MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        for abs_path, rel in files:
            try:
                zf.write(abs_path, rel)
            except OSError:
                # File vanished or is unreadable mid-archive: skip it.
                manifest["file_count"] -= 1
                continue
    return manifest


def backup_workspace(
    workspace: str,
    *,
    target_dir: str | None = None,
    include_derived: bool = False,
) -> dict:
    """Archive Notes/wiki/Raw + workspace metadata into a zip (derived indices excluded)."""
    if not workspace:
        return {"success": False, "message": "未设置工作区"}
    root = Path(workspace)
    if not root.is_dir():
        return {"success": False, "message": f"工作区不存在：{workspace}"}
    target = Path(target_dir) if target_dir else default_backup_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"success": False, "message": f"无法创建备份目录：{exc}"}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = target / f"noteai-backup-{stamp}.zip"
    files, skipped = collect_workspace_files(workspace, include_derived=include_derived)
    try:
        manifest = _write_zip(zip_path, workspace, files)
    except OSError as exc:
        return {"success": False, "message": f"备份写入失败：{exc}"}
    return {
        "success": True,
        "backup_path": str(zip_path),
        "size_bytes": zip_path.stat().st_size,
        "file_count": manifest["file_count"],
        "skipped": skipped,
        "created_at": manifest["created_at"],
    }


def export_notes(workspace: str, *, target_dir: str | None = None) -> dict:
    """Export pure user content (Notes/ + tags.md) as a shareable zip."""
    if not workspace:
        return {"success": False, "message": "未设置工作区"}
    root = Path(workspace)
    if not root.is_dir():
        return {"success": False, "message": f"工作区不存在：{workspace}"}
    target = Path(target_dir) if target_dir else default_backup_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"success": False, "message": f"无法创建导出目录：{exc}"}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = target / f"noteai-notes-{stamp}.zip"
    files, skipped = collect_workspace_files(workspace, export_only=True)
    try:
        manifest = _write_zip(zip_path, workspace, files)
    except OSError as exc:
        return {"success": False, "message": f"导出写入失败：{exc}"}
    return {
        "success": True,
        "backup_path": str(zip_path),
        "size_bytes": zip_path.stat().st_size,
        "file_count": manifest["file_count"],
        "skipped": skipped,
        "created_at": manifest["created_at"],
    }


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> list[str]:
    """Extract entries guarding against path traversal (zip-slip)."""
    extracted: list[str] = []
    target_resolved = target.resolve()
    for member in zf.infolist():
        raw = member.filename.replace("\\", "/")
        name = PurePosixPath(raw).name
        if not name or raw == _MANIFEST_NAME:
            continue
        clean = PurePosixPath(raw)
        if clean.is_absolute() or ".." in clean.parts:
            raise ValueError(f"备份文件包含非法路径：{raw}")
        dest = (target / clean).resolve()
        if dest != target_resolved and target_resolved not in dest.parents:
            raise ValueError(f"备份文件越界：{raw}")
        if member.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
        extracted.append(clean.as_posix())
    return extracted


def restore_workspace_backup(workspace: str, backup_path: str) -> dict:
    """Restore a backup zip into the workspace.

    Content folders already present are moved to ``.trash/restore-<ts>/``
    first, so an accidental restore is recoverable.
    """
    if not workspace:
        return {"success": False, "message": "未设置工作区"}
    zip_path = Path(backup_path)
    if not zip_path.is_file():
        return {"success": False, "message": f"备份文件不存在：{backup_path}"}
    root = Path(workspace)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"success": False, "message": f"无法创建工作区目录：{exc}"}
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if _MANIFEST_NAME not in names:
                return {"success": False, "message": "不是有效的 NoteAI 备份文件（缺少 manifest）"}
            manifest = json.loads(zf.read(_MANIFEST_NAME).decode("utf-8"))
            if manifest.get("app") != "NoteAI" or manifest.get("kind") != "workspace-backup":
                return {"success": False, "message": "备份文件类型不匹配"}
            top_dirs = set()
            for raw in names:
                clean = PurePosixPath(raw.replace("\\", "/"))
                if clean.is_absolute() or ".." in clean.parts:
                    # Rejected later by _safe_extract; never use them to move content.
                    continue
                posix = clean.as_posix()
                if "/" in posix or posix.endswith("/"):
                    top_dirs.add(clean.parts[0])
            trash = root / ".trash" / f"restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            for folder in sorted(top_dirs):
                src = root / folder
                if src.is_dir():
                    trash.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(trash / folder))
            extracted = _safe_extract(zf, root)
    except (zipfile.BadZipFile, ValueError, json.JSONDecodeError, OSError) as exc:
        return {"success": False, "message": f"恢复失败：{exc}"}
    return {
        "success": True,
        "restored_count": len(extracted),
        "workspace_name": manifest.get("workspace_name", ""),
        "created_at": manifest.get("created_at", ""),
        "note": "恢复完成后请重建 RAG 索引与语义库（索引不随备份迁移）",
    }


def check_index_health(workspace: str) -> dict:
    """Read-only health report for every derived index layer."""
    if not workspace:
        return {"success": False, "message": "未设置工作区"}
    root = Path(workspace)
    report: dict[str, Any] = {"success": True}

    # RAG collection + BM25.
    try:
        from sidecar.rag.index import index_exists, manifest_path

        rag_ok = index_exists(workspace)
        bm25_ok = (root / "zvec" / "bm25").exists() or (root / "bm25").exists()
        report["rag"] = {
            "ok": rag_ok,
            "detail": "索引存在" if rag_ok else "索引缺失，可重建",
            "bm25_ok": bm25_ok,
            "manifest_mtime": manifest_path(workspace).stat().st_mtime if manifest_path(workspace).exists() else None,
        }
    except Exception as exc:  # noqa: BLE001 - report must never raise
        report["rag"] = {"ok": False, "detail": f"检查失败：{exc}"}

    # Semantic store: present + compiled-document coverage.
    try:
        from sidecar.semantic.store import SemanticStore

        store = SemanticStore(workspace)
        store_ok = store.path.exists()
        compiled = 0
        if store_ok:
            with store.connect() as conn:
                compiled = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        notes = (
            sorted(p for p in (root / "Notes").rglob("*.md") if not p.name.startswith("."))
            if (root / "Notes").is_dir()
            else []
        )
        report["semantic"] = {
            "ok": store_ok,
            "detail": "语义库存在" if store_ok else "语义库缺失，可全量编译",
            "compiled_documents": compiled,
            "note_files": len(notes),
        }
    except Exception as exc:  # noqa: BLE001
        report["semantic"] = {"ok": False, "detail": f"检查失败：{exc}"}

    # Link index.
    links_path = root / ".links.json"
    try:
        if links_path.exists():
            json.loads(links_path.read_text(encoding="utf-8"))
            report["links"] = {"ok": True, "detail": "链接索引正常"}
        else:
            report["links"] = {"ok": True, "detail": "暂无链接索引"}
    except (json.JSONDecodeError, OSError) as exc:
        report["links"] = {"ok": False, "detail": f"链接索引损坏：{exc}"}

    # Full-text index rebuilds itself in memory; report capability only.
    report["fulltext"] = {"ok": True, "detail": "内存全文索引按需自愈"}
    return report
