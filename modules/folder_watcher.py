"""本机文件夹监控：监控用户指定目录，新增可消化文件时自动触发知识库导入。

与 RSS 订阅（sidecar/multi_source.py）同属"多源采集"能力，
复用 FileConverterManager / WebDownloader 的既有下载、解析与入库流程。
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from utils.logger import logger

_WATCH_FILE = "watched_folders.json"

# 可自动导入的格式：.md 之外与 FileConverterManager.get_supported_formats() 保持一致。
SUPPORTED_WATCHED_EXTENSIONS = {
    ".pdf",
    ".md",
    ".docx",
    ".doc",
    ".pptx",
    ".ppt",
    ".html",
    ".htm",
    ".txt",
}


def _watch_path(workspace: str) -> Path:
    return Path(workspace) / ".noteai" / _WATCH_FILE


def load_watched_folders(workspace: str) -> list[dict]:
    """读取已监控目录列表（与 rss_subscriptions.json 同级的持久化文件）。"""
    p = _watch_path(workspace)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_watched_folders(workspace: str, folders: list[dict]) -> None:
    p = _watch_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(folders, ensure_ascii=False, indent=2), encoding="utf-8")


def add_watched_folder(workspace: str, folder_path: str, recursive: bool = True) -> dict:
    """添加一个待监控目录（仅校验存在性，不校验归属）。"""
    path = (folder_path or "").strip()
    if not path:
        return {"success": False, "message": "文件夹路径为空"}
    p = Path(path).expanduser()
    if not p.is_dir():
        return {"success": False, "message": f"文件夹不存在: {p}"}

    folders = load_watched_folders(workspace)
    norm = str(p)
    if any(f.get("path") == norm for f in folders):
        return {"success": False, "message": f"已监控该文件夹: {p}"}

    folders.append(
        {
            "path": norm,
            "recursive": bool(recursive),
            "enabled": True,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_watched_folders(workspace, folders)
    return {"success": True, "message": f"已添加监控: {p}", "folders": folders}


def remove_watched_folder(workspace: str, folder_path: str) -> dict:
    """移除一个待监控目录。"""
    path = (folder_path or "").strip()
    folders = load_watched_folders(workspace)
    kept = [f for f in folders if f.get("path") != path]
    if len(kept) == len(folders):
        return {"success": False, "message": "未找到该监控目录"}
    save_watched_folders(workspace, kept)
    return {"success": True, "message": f"已移除监控: {path}", "folders": kept}


def is_supported_watch_file(file_path: str) -> bool:
    """判断文件是否属于可自动导入的格式（过滤隐藏文件与目录）。"""
    p = Path(file_path)
    return p.is_file() and not p.name.startswith(".") and p.suffix.lower() in SUPPORTED_WATCHED_EXTENSIONS


def collect_ingestible_files(folder: str, recursive: bool = True) -> list[str]:
    """全量扫描目录，收集当前可导入的文件（用于"立即扫描"场景）。"""
    root = Path(folder).expanduser()
    if not root.is_dir():
        return []
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(str(p) for p in iterator if is_supported_watch_file(str(p)))


class _FolderWatchHandler(FileSystemEventHandler):
    """文件夹变化处理器：关注"新增文件"场景，交由 FolderWatcher 统一回调。"""

    def __init__(self, watcher: FolderWatcher):
        self._watcher = watcher

    def on_created(self, event):
        if event.is_directory:
            return
        self._watcher._queue_file(event.src_path)


class FolderWatcher:
    """监控一组本机文件夹，新增可消化文件时触发入库回调。

    Args:
        on_files: 收集到新增文件后的回调（接收文件路径列表），由调用方执行
            实际的解析与入库（如复制到 Raw 后走 FileConverterManager）。
    """

    def __init__(self, on_files: Callable[[list[str]], None]):
        self._on_files = on_files
        self._observer: Any | None = None
        self._lock = threading.Lock()

    def start(self, folders: list[dict]) -> None:
        """按配置启动监控；不存在的目录会被自动跳过。"""
        self.stop()
        entries = [f for f in folders or [] if f.get("enabled", True) and f.get("path")]
        if not entries:
            return
        try:
            observer = Observer()
            handler = _FolderWatchHandler(self)
            scheduled = 0
            for entry in entries:
                path = Path(entry["path"]).expanduser()
                if not path.is_dir():
                    logger.warning(f"[folder_watcher] 目录不存在，跳过监控: {path}")
                    continue
                observer.schedule(handler, str(path), recursive=bool(entry.get("recursive", True)))
                scheduled += 1
            if scheduled == 0:
                return
            observer.daemon = True
            observer.start()
            self._observer = observer
            logger.info(f"[folder_watcher] 已开始监控 {scheduled} 个目录")
        except Exception as e:
            logger.warning(f"[folder_watcher] 启动监控失败: {e}")

    def stop(self) -> None:
        if self._observer:
            try:
                self._observer.stop()
                self._observer.join(timeout=5)
            except Exception as e:
                logger.warning(f"[folder_watcher] 停止监控失败: {e}")
            self._observer = None

    def _queue_file(self, file_path: str) -> None:
        """新增文件过滤后交给回调处理（异步，避免阻塞 watchdog 线程）。"""
        p = Path(file_path)
        if p.name.startswith(".") or p.suffix.lower() not in SUPPORTED_WATCHED_EXTENSIONS:
            return
        if not is_supported_watch_file(file_path):
            # created 事件可能先于文件完整落盘，短暂等待后重试
            for _ in range(3):
                time.sleep(0.3)
                if is_supported_watch_file(file_path):
                    break
            else:
                logger.debug(f"[folder_watcher] 文件未就绪，跳过: {file_path}")
                return
        logger.info(f"[folder_watcher] 检测到新文件: {file_path}")
        threading.Thread(target=self._invoke_callback, args=(file_path,), daemon=True).start()

    def _invoke_callback(self, file_path: str) -> None:
        try:
            self._on_files([file_path])
        except Exception as e:
            logger.warning(f"[folder_watcher] 处理新增文件失败 {file_path}: {e}")
