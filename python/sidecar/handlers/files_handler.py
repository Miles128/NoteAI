import base64
import importlib
import platform
import subprocess
from pathlib import Path

from sidecar.handlers.base import BaseHandler
from utils.logger import logger
from utils.topic_assigner import sync_wiki_with_files

_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MiB


class FilesHandler(BaseHandler):
    PREVIEW_LARGE_RAW_UTF8_THRESHOLD = 512 * 1024
    RAW_SLICE_EXTENSIONS = frozenset({".md", ".markdown", ".txt"})
    RAW_SLICE_MAX = 786_432

    def _resolved_preview_full_path(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            full_path = self._find_file_by_name(path)
        if not full_path:
            return None
        if not Path(full_path).exists():
            alt = self._find_file_by_name(path)
            if alt:
                full_path = alt
        return full_path if Path(full_path).exists() else None

    def _head_looks_utf8(self, blob: bytes) -> bool:
        if not blob:
            return True
        try:
            blob.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True

    def _get_file_preview(self, params):
        full_path = self._resolved_preview_full_path(params)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        resolved = Path(full_path)
        ext = resolved.suffix.lower()
        if ext in self.RAW_SLICE_EXTENSIONS:
            sz = resolved.stat().st_size
            take = min(8192, sz)
            header = resolved.read_bytes()[:take] if take else b""
            if (
                not bool(params.get("force_semantic_preview"))
                and sz > self.PREVIEW_LARGE_RAW_UTF8_THRESHOLD
                and self._head_looks_utf8(header)
            ):
                return {
                    "success": True,
                    "type": "markdown" if ext != ".txt" else "text",
                    "preview_delivery": "raw_slices",
                    "file_name": resolved.name,
                    "file_size": sz,
                    "total_byte_size": sz,
                    "transport_hint": "raw_utf8",
                }

        return self.file_previewer.get_preview_data(full_path)

    def _read_preview_raw_slice(self, params):
        full_path = self._resolved_preview_full_path(params)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        resolved = Path(full_path)
        ext = resolved.suffix.lower()
        if ext not in self.RAW_SLICE_EXTENSIONS:
            return {"success": False, "message": "不支持对该类型分页读取"}

        offset = params.get("byte_offset", 0)
        byte_limit = params.get("byte_limit", 392_192)
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0
        try:
            limit_req = max(1, int(byte_limit))
        except (TypeError, ValueError):
            limit_req = 392_192
        limit_req = min(limit_req, self.RAW_SLICE_MAX)

        sz = resolved.stat().st_size
        offset = min(offset, sz)
        remaining = sz - offset
        read_len = min(limit_req, remaining)
        with resolved.open("rb") as fh:
            fh.seek(offset)
            blob = fh.read(read_len)
        next_off = offset + len(blob)

        return {
            "success": True,
            "chunk_b64": base64.b64encode(blob).decode("ascii"),
            "total_byte_size": sz,
            "byte_offset_start": offset,
            "next_byte_offset": next_off,
            "done": next_off >= sz,
        }

    def _can_preview_file(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            full_path = self._find_file_by_name(path)
        if not full_path:
            return False
        return self.file_previewer.can_preview(full_path)

    def _save_file_content(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        content = params.get("content", "")
        if len(content.encode("utf-8")) > _MAX_FILE_SIZE_BYTES:
            return {"success": False, "message": "文件内容超过最大限制"}
        try:
            full = Path(full_path)
            rel_path = ""
            workspace = self.config.workspace_path
            if workspace:
                try:
                    rel_path = str(full.relative_to(Path(workspace)))
                except ValueError:
                    rel_path = str(full_path)
            full.write_text(content, encoding="utf-8")
            if rel_path.lower().endswith(".md"):
                self._start_task(
                    f"suggest_links_{Path(rel_path).stem}",
                    self._do_suggest_links_for_file,
                    args=(rel_path,),
                )
            return {"success": True, "message": "文件已保存"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _do_suggest_links_for_file(self, rel_path: str) -> None:
        from utils.link_indexer import discover_cross_refs_for_file

        discover_cross_refs_for_file(rel_path)

    def _read_file_raw(self, params):
        path = params.get("path", "")
        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        try:
            full = Path(full_path)
            if full.exists() and full.stat().st_size > _MAX_FILE_SIZE_BYTES:
                return {"success": False, "message": "文件超过最大读取限制"}
            raw_bytes = full.read_bytes()
            return {
                "success": True,
                "content": base64.b64encode(raw_bytes).decode("utf-8"),
                "size": len(raw_bytes),
                "file_name": Path(full_path).name,
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _reveal_in_finder(self, params):
        import shutil

        path = params.get("path", "")
        if not path:
            return {"success": False, "message": "路径不能为空"}

        resolved = self._resolve_path(path)
        if resolved is None:
            return {"success": False, "message": "路径不允许在工作区外"}
        resolved_path = Path(resolved)
        if not resolved_path.exists():
            return {"success": False, "message": "解析后的路径不存在"}

        # Reject paths with control characters or shell metacharacters that could confuse external commands.
        if any(ord(ch) < 32 for ch in resolved) or '"' in resolved or '&' in resolved or '|' in resolved:
            return {"success": False, "message": "路径包含非法字符"}

        try:
            if platform.system() == "Darwin":
                cmd = shutil.which("open")
                if not cmd:
                    return {"success": False, "message": "系统未找到 open 命令"}
                # "--" prevents paths starting with "-" from being parsed as options.
                subprocess.Popen([cmd, "-R", "--", str(resolved_path)])
            elif platform.system() == "Windows":
                cmd = shutil.which("explorer")
                if not cmd:
                    return {"success": False, "message": "系统未找到 explorer 命令"}
                # Quote the path so explorer sees it as a single argument.
                subprocess.Popen([cmd, f'/select,"{resolved_path}"'])
            else:
                cmd = shutil.which("xdg-open") or shutil.which("nautilus") or shutil.which("dolphin")
                if not cmd:
                    return {"success": False, "message": "系统未找到文件管理器命令"}
                parent = resolved_path.parent
                if not parent.exists():
                    return {"success": False, "message": "父目录不存在"}
                subprocess.Popen([cmd, str(parent)])
            return {"success": True}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _delete_file(self, params):
        path = params.get("path", "")
        if not path:
            return {"success": False, "message": "路径不能为空"}

        full_path = self._resolve_path(path)
        if not full_path:
            return {"success": False, "message": "路径无效"}
        full_path = Path(full_path)

        if not full_path.exists():
            return {"success": False, "message": "文件不存在"}

        if not full_path.is_file():
            return {"success": False, "message": "只能删除文件，不能删除目录"}

        workspace = self.config.workspace_path
        if workspace:
            ws_path = Path(workspace).resolve()
            resolved_path = full_path.resolve()
            try:
                rel = resolved_path.relative_to(ws_path)
            except ValueError:
                return {"success": False, "message": "只能删除工作区内的文件"}
            # 保护关键目录本身不被删除（虽然 is_file 已拦截目录，但保留边界校验）
            protected_roots = {"Notes", "wiki", "Raw", ".noteai", ".ai_memory"}
            if rel.parts and rel.parts[0] in protected_roots and len(rel.parts) <= 1:
                return {"success": False, "message": "不能删除工作区的核心目录"}
            if resolved_path == ws_path:
                return {"success": False, "message": "不能删除工作区根目录"}

        file_topic = None
        if full_path.suffix.lower() == ".md":
            try:
                text = full_path.read_text(encoding="utf-8")
                meta, _ = self._parse_frontmatter(text)
                if meta and isinstance(meta.get("topic"), str):
                    file_topic = meta["topic"].strip().strip("'\"")
            except Exception as e:
                logger.warning(f"[files_handler] reading file topic for deletion: {e}\n")

        try:
            send2trash = importlib.import_module("send2trash")
            send2trash.send2trash(str(full_path))

            if full_path.suffix.lower() == ".md":
                try:
                    sync_wiki_with_files()
                except Exception as e:
                    logger.warning(f"[files_handler] syncing WIKI after file deletion: {e}\n")

            if file_topic:
                self._start_task(f"cascade_update_{file_topic}", self._do_cascade_survey_update, args=(file_topic,))

            return {"success": True}
        except ImportError:
            return {
                "success": False,
                "message": "未安装 send2trash，无法安全删除文件。请运行: uv pip install send2trash",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _create_note(self, params):
        from config.constants import TOPIC_SEP
        from config.settings import NOTES_FOLDER
        from sidecar.schema_validator import require_topic
        from utils.helpers import sanitize_filename

        title = (params.get("title") or "").strip()
        topic = (params.get("topic") or "").strip()
        if not title:
            return {"success": False, "message": "标题不能为空"}

        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}

        if topic:
            ok, err = require_topic(topic)
            if not ok:
                return {"success": False, "message": err}

        ws = Path(workspace)
        notes_root = ws / NOTES_FOLDER
        if topic:
            parts = [p.strip() for p in topic.split(TOPIC_SEP) if p.strip()]
            target_dir = notes_root
            for part in parts:
                target_dir = target_dir / part
        else:
            target_dir = notes_root / "_未分类"

        target_dir.mkdir(parents=True, exist_ok=True)
        stem = sanitize_filename(title) or "未命名"
        candidate = target_dir / f"{stem}.md"
        if candidate.exists():
            n = 2
            while candidate.exists():
                candidate = target_dir / f"{stem}_{n}.md"
                n += 1

        fm_lines = ["---"]
        if topic:
            fm_lines.append(f"topic: {topic}")
        fm_lines.append("---")
        body = f"# {title}\n\n"
        candidate.write_text("\n".join(fm_lines) + "\n\n" + body, encoding="utf-8")
        rel = str(candidate.relative_to(ws))

        from sidecar.cascade import append_changelog

        append_changelog(f"新建笔记: {rel}" + (f"（{topic}）" if topic else ""))

        return {
            "success": True,
            "path": rel,
            "title": title,
            "topic": topic,
            "message": f"已创建 {rel}",
        }

    def register_routes(self, router):
        router.register("get_file_preview", self._get_file_preview)
        router.register("read_preview_raw_slice", self._read_preview_raw_slice)
        router.register("can_preview_file", self._can_preview_file)
        router.register("save_file_content", self._save_file_content)
        router.register("create_note", self._create_note)
        router.register("read_file_raw", self._read_file_raw)
        router.register("reveal_in_finder", self._reveal_in_finder)
        router.register("delete_file", self._delete_file)
