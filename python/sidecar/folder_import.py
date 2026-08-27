"""Workspace folder import and auto-convert (moved out of SidecarServer)."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from config import config
from config.settings import NOTES_FOLDER, RAW_FOLDER
from utils.logger import logger


def convert_new_workspace_file(file_path: str, send_response: Callable[[dict], None] | None = None) -> dict | None:
    """Convert a newly added non-markdown file into Notes/. Returns converter result."""
    from modules.file_converter import FileConverterManager
    from sidecar.convert_failures import record_convert_batch_results

    ws = config.workspace_path
    if not ws:
        return None
    converter = FileConverterManager()
    output_dir = str(Path(ws) / config.NOTES_FOLDER)
    raw_dir = str(Path(ws) / config.RAW_FOLDER)
    result = converter.convert_file(file_path, output_dir, raw_path=raw_dir)
    record_convert_batch_results([result])
    if result and result.get("success"):
        md = result.get("output_path", "")
        if md and send_response:
            send_response(
                {
                    "id": "event",
                    "result": {
                        "type": "auto_file_converted",
                        "data": {"source": file_path, "markdown": md},
                    },
                }
            )
    return result


def import_markdown_file(src: Path, notes_dir: Path) -> dict:
    """Copy a watched-folder .md into Notes, filling missing frontmatter."""
    from utils.helpers import sanitize_filename
    from utils.tag_extractor import add_yaml_frontmatter_to_content
    from utils.text_utils import parse_frontmatter

    try:
        text = src.read_text(encoding="utf-8", errors="replace")
        meta, _body = parse_frontmatter(text)
        title = str((meta or {}).get("title") or src.stem).strip() or src.stem
        content = text if meta else add_yaml_frontmatter_to_content(text, title=title, tags=[], source=str(src))
        stem = sanitize_filename(title)
        dest = notes_dir / f"{stem}.md"
        counter = 1
        while dest.exists():
            dest = notes_dir / f"{stem}_{counter}.md"
            counter += 1
        dest.write_text(content, encoding="utf-8")
        return {"success": True, "source": str(src), "output_path": str(dest), "title": title}
    except Exception as e:
        logger.warning(f"[folder_watcher] 导入 Markdown 失败 {src}: {e}")
        return {"success": False, "source": str(src), "error": str(e)}


def handle_watched_folder_files(
    files: list[str],
    *,
    file_converter: Any,
    send_response: Callable[[dict], None],
) -> None:
    """Import files from a watched folder into Notes/Raw."""
    workspace = config.workspace_path
    if not workspace or not files:
        return
    ws = Path(workspace)
    raw_dir = ws / RAW_FOLDER
    raw_dir.mkdir(parents=True, exist_ok=True)
    notes_dir = ws / NOTES_FOLDER
    notes_dir.mkdir(parents=True, exist_ok=True)

    supported = set(file_converter.get_supported_formats())
    results: list[dict] = []
    copied: list[str] = []
    for f in files:
        src = Path(f)
        if not src.is_file():
            continue
        if src.suffix.lower() == ".md":
            results.append(import_markdown_file(src, notes_dir))
            continue
        if src.suffix.lower() not in supported:
            results.append({"success": False, "source": str(src), "error": f"不支持的格式: {src.suffix}"})
            continue
        dst = raw_dir / src.name
        counter = 1
        while dst.exists():
            dst = raw_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1
        try:
            shutil.copy2(str(src), str(dst))
            copied.append(str(dst))
        except Exception as e:
            results.append({"success": False, "source": str(src), "error": str(e)})

    if copied:
        batch = file_converter.convert_batch(copied, str(notes_dir))
        results.extend(batch)
        try:
            from sidecar.convert_failures import record_convert_batch_results

            record_convert_batch_results(batch)
        except Exception as e:
            logger.warning(f"[folder_watcher] 记录转换结果失败: {e}")

    success_count = sum(1 for r in results if r.get("success"))
    send_response(
        {
            "id": "event",
            "result": {
                "type": "folder_watch_complete",
                "data": {"total": len(results), "imported": success_count, "results": results},
            },
        }
    )
    logger.info(f"[folder_watcher] 导入完成: {success_count}/{len(results)} 个文件")
