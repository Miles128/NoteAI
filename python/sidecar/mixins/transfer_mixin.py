"""Web download, import, conversion, topic extract, note integration (from python/main.py)."""

import json
import re
import sys
import shutil
import threading
from pathlib import Path

import yaml
from config import config, is_ignored_dir
from modules.note_integration import NoteIntegration

class TransferMixin:
    def _start_web_download(self, params):
        urls = params.get("urls", [])
        ai_assist = params.get("ai_assist", False)
        include_images = params.get("include_images", True)
        save_path = config.workspace_path
        if not save_path:
            return {"success": False, "message": "请先设置工作区"}
        if not urls:
            return {"success": False, "message": "请输入至少一个URL"}

        if not self._start_task("web_download", self._do_web_download, args=(urls, save_path, ai_assist, include_images)):
            return {"success": False, "message": "下载任务正在进行中，请稍后"}

        return {"success": True, "message": "下载已开始"}

    def _do_web_download(self, urls, save_path, ai_assist, include_images):
        try:
            def progress_cb(current, total, message):
                self._send_progress("web-progress", current / total if total > 0 else 0, message)

            self.web_downloader.progress_callback = progress_cb
            self.web_downloader.ai_assist = ai_assist
            self.web_downloader.include_images = include_images
            result = self.web_downloader.download_batch(urls, save_path)
            success_count = sum(1 for r in result if r.get("success"))
            self._send_response({
                "id": "event",
                "result": {"type": "web_download_complete", "success_count": success_count, "total": len(result), "data": result}
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] web_download: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "web_download_error", "error": str(e)}
            })

    def _import_files(self, params):
        import shutil
        files = params.get("files", [])
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}
        if not files:
            return {"success": False, "message": "未选择文件"}

        raw_dir = Path(workspace) / "Raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        supported_exts = set(self.file_converter.get_supported_formats())
        copied = []
        skipped = []
        for src in files:
            src_path = Path(src)
            if not src_path.exists():
                skipped.append({"file": src, "reason": "文件不存在"})
                continue
            ext = src_path.suffix.lower()
            if ext not in supported_exts:
                skipped.append({"file": src, "reason": f"不支持的格式: {ext}"})
                continue
            try:
                dst = raw_dir / src_path.name
                if dst.exists():
                    stem = src_path.stem
                    counter = 1
                    while dst.exists():
                        dst = raw_dir / f"{stem}_{counter}{src_path.suffix}"
                        counter += 1
                shutil.copy2(str(src_path), str(dst))
                copied.append(str(dst))
            except Exception as e:
                skipped.append({"file": src, "reason": str(e)})

        if not copied:
            return {"success": False, "message": "没有可导入的文件", "skipped": skipped}

        if not self._start_task("file_import", self._do_file_import, args=(copied, workspace, skipped)):
            return {"success": False, "message": "导入任务正在进行中，请稍后"}

        return {"success": True, "message": "导入已开始", "file_count": len(copied)}

    def _do_file_import(self, copied, workspace, skipped):
        try:
            total = len(copied)
            for i, f in enumerate(copied):
                self._send_progress("import-progress", (i + 1) / total, f"正在转换 {i + 1}/{total}")

            result = self.file_converter.convert_batch(copied, workspace)
            success_count = sum(1 for r in result if r.get("success"))
            fail_count = sum(1 for r in result if not r.get("success"))

            try:
                from utils.tag_extractor import save_tags_md
                if workspace:
                    save_tags_md(workspace)
            except Exception:
                pass

            self._send_response({
                "id": "event",
                "result": {
                    "type": "file_import_complete",
                    "data": {
                        "success": True,
                        "imported": success_count,
                        "failed": fail_count + len(skipped),
                        "skipped": skipped
                    }
                }
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] file_import: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "file_import_error", "error": str(e)}
            })

    def _start_file_conversion(self, params):
        ai_assist = params.get("ai_assist", False)
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        if not self._start_task("file_conversion", self._do_file_conversion, args=(workspace, ai_assist)):
            return {"success": False, "message": "转换任务正在进行中，请稍后"}

        return {"success": True, "message": "转换已开始"}

    def _do_file_conversion(self, workspace, ai_assist):
        try:
            result = self.file_converter.convert_folder(
                workspace, ai_assist=ai_assist
            )
            self._send_response({
                "id": "event",
                "result": {"type": "file_conversion_complete", "data": result}
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] file_conversion: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "file_conversion_error", "error": str(e)}
            })
    def _extract_topics(self, params):
        topic_count = params.get("topic_count", None)
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        result = self.topic_extractor.extract_topics(
            workspace, topic_count=topic_count
        )
        if not result.get("success"):
            return {"success": False, "message": result.get("error", "提取主题失败")}
        return result
    def _start_note_integration(self, params):
        auto_topic = params.get("auto_topic", True)
        topics = params.get("topics", [])
        workspace = config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        self.note_integration = NoteIntegration()

        if not self._start_task("note_integration", self._do_note_integration, args=(workspace, auto_topic, topics)):
            return {"success": False, "message": "整合任务正在进行中，请稍后"}

        return {"success": True, "message": "整合已开始"}

    def _do_note_integration(self, workspace, auto_topic, topics):
        try:
            documents = self.note_integration.load_documents_from_folder(workspace)
            result = self.note_integration.integrate(
                documents=documents,
                save_path=workspace,
                user_topics=topics if topics else None
            )
            self._send_response({
                "id": "event",
                "result": {"type": "note_integration_complete", "data": result}
            })
        except Exception as e:
            import traceback
            sys.stderr.write(f"[ERROR] note_integration: {e}\n{traceback.format_exc()}")
            sys.stderr.flush()
            self._send_response({
                "id": "event",
                "result": {"type": "note_integration_error", "error": str(e)}
            })
