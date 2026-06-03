import shutil
import traceback
from pathlib import Path

from config.settings import NOTES_FOLDER, RAW_FOLDER
from modules.file_converter import FileConverterManager
from modules.note_integration import NoteIntegration
from sidecar.convert_failures import (
    clear_convert_failure,
    load_convert_failures,
    record_convert_batch_results,
)
from sidecar.handlers.base import BaseHandler
from utils.logger import logger


class TransferHandler(BaseHandler):
    def register_routes(self, router):
        router.register("start_web_download", self._start_web_download)
        router.register("import_files", self._import_files)
        router.register("start_file_conversion", self._start_file_conversion)
        router.register("auto_convert_pending", self._auto_convert_pending)
        router.register("extract_topics", self._extract_topics)
        router.register("start_note_integration", self._start_note_integration)
        router.register("get_convert_failures", self._get_convert_failures)
        router.register("retry_convert_file", self._retry_convert_file)
        router.register("retry_all_convert_failures", self._retry_all_convert_failures)
        router.register("dismiss_convert_failure", self._dismiss_convert_failure)
        router.register("import_rss_feed", self._import_rss_feed)
        router.register("import_transcript", self._import_transcript)
        router.register("convert_raw_archive", self._convert_raw_archive)

    def _start_web_download(self, params):
        urls = params.get("urls", [])
        ai_assist = params.get("ai_assist", False)
        include_images = params.get("include_images", True)
        save_path = self.config.workspace_path
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
            logger.warning(f"[ERROR] web_download: {e}\n{traceback.format_exc()}")
            self._send_response({
                "id": "event",
                "result": {"type": "web_download_error", "error": str(e)}
            })

    def _import_files(self, params):

        files = params.get("files", [])
        workspace = self.config.workspace_path
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
            for i, _f in enumerate(copied):
                self._send_progress("import-progress", (i + 1) / total, f"正在转换 {i + 1}/{total}")

            result = self.file_converter.convert_batch(copied, workspace)
            from sidecar.convert_failures import record_convert_batch_results

            record_convert_batch_results(result)
            success_count = sum(1 for r in result if r.get("success"))
            fail_count = sum(1 for r in result if not r.get("success"))

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
            logger.warning(f"[ERROR] file_import: {e}\n{traceback.format_exc()}")
            self._send_response({
                "id": "event",
                "result": {"type": "file_import_error", "error": str(e)}
            })

    def _start_file_conversion(self, params):
        ai_assist = params.get("ai_assist", False)
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        if not self._start_task("file_conversion", self._do_file_conversion, args=(workspace, ai_assist)):
            return {"success": False, "message": "转换任务正在进行中，请稍后"}

        return {"success": True, "message": "转换已开始"}

    def _do_file_conversion(self, workspace, ai_assist):
        _ = ai_assist
        try:
            result = self.file_converter.convert_folder(
                workspace,
                output_path=str(Path(workspace) / NOTES_FOLDER),
                raw_path=str(Path(workspace) / RAW_FOLDER),
            )
            self._send_response({
                "id": "event",
                "result": {"type": "file_conversion_complete", "data": result}
            })
        except Exception as e:
            logger.warning(f"[ERROR] file_conversion: {e}\n{traceback.format_exc()}")
            self._send_response({
                "id": "event",
                "result": {"type": "file_conversion_error", "error": str(e)}
            })

    def _auto_convert_pending(self, _params=None):
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "pending": 0, "converted": 0}

        supported = set(FileConverterManager.get_supported_formats())
        ws = Path(workspace)
        ws / RAW_FOLDER

        pending = []
        for f in ws.rglob('*'):
            if not f.is_file() or f.name.startswith('.'):
                continue
            rel = f.relative_to(ws)
            if any(part.startswith('.') for part in rel.parts):
                continue
            if RAW_FOLDER in rel.parts:
                continue
            if f.suffix.lower() in supported:
                pending.append(str(f))

        if not pending:
            return {"success": True, "pending": 0, "converted": 0}

        if not self._start_task("auto_convert", self._do_auto_convert, args=(workspace, pending)):
            return {"success": False, "pending": len(pending), "converted": 0, "message": "转换任务正在进行中"}

        return {"success": True, "pending": len(pending), "converted": 0}

    def _do_auto_convert(self, workspace, pending_files):
        try:
            raw_path = str(Path(workspace) / "Raw")
            results = self.file_converter.convert_batch(
                pending_files, workspace, raw_path=raw_path
            )
            from sidecar.convert_failures import record_convert_batch_results

            record_convert_batch_results(results)
            converted = sum(1 for r in results if r.get("success"))
            failed = sum(1 for r in results if not r.get("success"))
            self._send_response({
                "id": "event",
                "result": {
                    "type": "auto_convert_complete",
                    "data": {
                        "total": len(pending_files),
                        "converted": converted,
                        "failed": failed,
                    },
                },
            })
        except Exception as e:
            logger.warning(f"[ERROR] auto_convert: {e}\n{traceback.format_exc()}")
            self._send_response({
                "id": "event",
                "result": {"type": "auto_convert_error", "error": str(e)}
            })

    def _get_convert_failures(self, _params):
        return {"success": True, "items": load_convert_failures()}

    def _retry_convert_file(self, params):
        file_path = (params.get("file") or params.get("path") or "").strip()
        workspace = self.config.workspace_path
        if not workspace or not file_path:
            return {"success": False, "message": "参数缺失"}
        if not self._start_task(f"convert_retry_{Path(file_path).stem}", self._do_retry_convert, args=(file_path, workspace)):
            return {"success": False, "message": "转换任务正在进行中"}
        return {"success": True, "message": f"已开始重试转换：{file_path}"}

    def _do_retry_convert(self, file_path: str, workspace: str) -> None:
        ws = Path(workspace)
        full = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)
        if not full.exists():
            record_convert_batch_results([{"success": False, "source": file_path, "error": "文件不存在"}])
            return
        raw_path = str(ws / RAW_FOLDER)
        results = self.file_converter.convert_batch([str(full)], workspace, raw_path=raw_path)
        record_convert_batch_results(results)

    def _retry_all_convert_failures(self, _params):
        items = load_convert_failures()
        files = [x.get("file") for x in items if x.get("file")]
        if not files:
            return {"success": True, "message": "无失败项"}
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "未设置工作区"}
        if not self._start_task("convert_retry_all", self._do_retry_all_converts, args=(files, workspace)):
            return {"success": False, "message": "转换任务正在进行中"}
        return {"success": True, "message": f"已开始重试 {len(files)} 个文件"}

    def _do_retry_all_converts(self, files: list[str], workspace: str) -> None:
        ws = Path(workspace)
        paths = []
        for rel in files:
            full = ws / rel
            if full.exists():
                paths.append(str(full))
        if not paths:
            return
        raw_path = str(ws / RAW_FOLDER)
        results = self.file_converter.convert_batch(paths, workspace, raw_path=raw_path)
        record_convert_batch_results(results)

    def _dismiss_convert_failure(self, params):
        file_path = (params.get("file") or params.get("path") or "").strip()
        if not file_path:
            return {"success": False, "message": "缺少文件路径"}
        clear_convert_failure(file_path)
        return {"success": True, "message": f"已忽略：{file_path}"}

    def _extract_topics(self, params):
        topic_count = params.get("topic_count", None)
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        result = self.topic_extractor.extract_topics(
            specified_topic_count=topic_count
        )
        if not result.get("success"):
            return {"success": False, "message": result.get("error", "提取主题失败")}
        return result

    def _start_note_integration(self, params):
        auto_topic = params.get("auto_topic", True)
        topics = params.get("topics", [])
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        self._server.note_integration = NoteIntegration()

        if not self._start_task("note_integration", self._do_note_integration, args=(workspace, auto_topic, topics)):
            return {"success": False, "message": "整合任务正在进行中，请稍后"}

        return {"success": True, "message": "整合已开始"}

    def _do_note_integration(self, workspace, auto_topic, topics):
        _ = auto_topic
        try:
            documents = self.note_integration.load_documents_from_folder(workspace)
            result = self.note_integration.integrate(
                documents=documents,
                save_path=workspace,
                user_topics=topics if topics else None
            )
            self.note_integration.documents = []
            self._send_response({
                "id": "event",
                "result": {"type": "note_integration_complete", "data": result}
            })
        except Exception as e:
            if self.note_integration:
                self.note_integration.documents = []
            logger.warning(f"[ERROR] note_integration: {e}\n{traceback.format_exc()}")
            self._send_response({
                "id": "event",
                "result": {"type": "note_integration_error", "error": str(e)}
            })

    def _import_rss_feed(self, params):
        from sidecar.multi_source import import_rss_feed

        url = params.get("url", "")
        max_items = int(params.get("max_items", 10) or 10)
        fetch_articles = bool(params.get("fetch_articles", True))
        if not self.config.workspace_path:
            return {"success": False, "message": "请先设置工作区"}
        return import_rss_feed(url, max_items=max_items, fetch_articles=fetch_articles)

    def _import_transcript(self, params):
        from sidecar.multi_source import import_transcript

        if not self.config.workspace_path:
            return {"success": False, "message": "请先设置工作区"}
        return import_transcript(
            params.get("title", ""),
            params.get("content", ""),
            source=params.get("source", ""),
            speakers=params.get("speakers", ""),
        )

    def _convert_raw_archive(self, _params):
        """Batch re-convert supported files under Raw/."""
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "请先设置工作区"}

        if not self._start_task("convert_raw", self._do_convert_raw_archive, args=(workspace,)):
            return {"success": False, "message": "转换任务正在进行中"}

        return {"success": True, "message": "Raw 批量转换已开始", "status": "started"}

    def _do_convert_raw_archive(self, workspace: str) -> None:
        supported = set(FileConverterManager.get_supported_formats())
        ws = Path(workspace)
        raw_root = ws / RAW_FOLDER
        pending: list[str] = []
        if raw_root.exists():
            for f in raw_root.rglob("*"):
                if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in supported:
                    pending.append(str(f))
        if not pending:
            self._send_response({
                "id": "event",
                "result": {
                    "type": "raw_convert_complete",
                    "success": True,
                    "converted": 0,
                    "message": "Raw/ 下无可转换文件",
                },
            })
            return
        raw_path = str(raw_root)
        results = self.file_converter.convert_batch(pending, workspace, raw_path=raw_path)
        record_convert_batch_results(results)
        converted = sum(1 for r in results if r.get("success"))
        self._send_response({
            "id": "event",
            "result": {
                "type": "raw_convert_complete",
                "success": True,
                "converted": converted,
                "total": len(pending),
                "message": f"Raw 转换完成: {converted}/{len(pending)}",
            },
        })

