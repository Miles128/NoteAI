import shutil
import traceback
from pathlib import Path

from config.settings import NOTES_FOLDER, RAW_FOLDER
from modules.file_converter import FileConverterManager
from modules.note_integration import NoteIntegration
from sidecar import job_status
from sidecar.convert_failures import (
    clear_convert_failure,
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
        router.register("retry_convert_file", self._retry_convert_file)
        router.register("dismiss_convert_failure", self._dismiss_convert_failure)
        router.register("import_rss_feed", self._import_rss_feed)
        router.register("import_transcript", self._import_transcript)
        router.register("save_rss_subscription", self._save_rss_subscription)
        router.register("remove_rss_subscription", self._remove_rss_subscription)
        router.register("list_rss_subscriptions", self._list_rss_subscriptions)
        router.register("fetch_all_rss", self._fetch_all_rss)
        router.register("list_watched_folders", self._list_watched_folders)
        router.register("add_watched_folder", self._add_watched_folder)
        router.register("remove_watched_folder", self._remove_watched_folder)
        router.register("scan_watched_folder", self._scan_watched_folder)

    def _run_sync_job(
        self,
        job_id: str,
        *,
        kind: str,
        label: str,
        message: str,
        metadata: dict | None,
        fn,
        complete_message,
        complete_metadata=None,
    ):
        job_status.start_job(
            job_id,
            kind=kind,
            label=label,
            message=message,
            metadata=metadata,
            send_event=self._send_response,
        )
        try:
            result = fn()
            if result.get("success"):
                job_status.complete_job(
                    job_id,
                    message=complete_message(result),
                    metadata=complete_metadata(result) if complete_metadata else None,
                    send_event=self._send_response,
                )
                return result
            job_status.fail_job(job_id, result.get("message", "任务失败"), send_event=self._send_response)
            return result
        except Exception as e:
            job_status.fail_job(job_id, str(e), send_event=self._send_response)
            raise

    def _start_web_download(self, params):
        urls = params.get("urls", [])
        ai_assist = params.get("ai_assist", False)
        include_images = params.get("include_images", True)
        save_path, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
        if not urls:
            return {"success": False, "message": "请输入至少一个URL"}

        if not self._start_task(
            "web_download",
            self._do_web_download,
            args=(urls, save_path, ai_assist, include_images),
            kind="ingest",
            label="Web download",
        ):
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
            self._send_response(
                {
                    "id": "event",
                    "result": {
                        "type": "web_download_complete",
                        "success_count": success_count,
                        "total": len(result),
                        "data": result,
                    },
                }
            )
        except Exception as e:
            logger.warning(f"[ERROR] web_download: {e}\n{traceback.format_exc()}")
            self._send_response({"id": "event", "result": {"type": "web_download_error", "error": str(e)}})

    def _import_files(self, params):

        files = params.get("files", [])
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
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

        if not self._start_task(
            "file_import",
            self._do_file_import,
            args=(copied, workspace, skipped),
            kind="conversion",
            label="File import",
        ):
            return {"success": False, "message": "导入任务正在进行中，请稍后"}

        return {"success": True, "message": "导入已开始", "file_count": len(copied)}

    def _do_file_import(self, copied, workspace, skipped):
        try:
            total = len(copied)
            for i, _f in enumerate(copied):
                self._send_progress("import-progress", (i + 1) / total, f"正在转换 {i + 1}/{total}")

            output_path = str(Path(workspace) / NOTES_FOLDER)
            result = self.file_converter.convert_batch(copied, output_path)
            from sidecar.convert_failures import record_convert_batch_results

            record_convert_batch_results(result)
            success_count = sum(1 for r in result if r.get("success"))
            fail_count = sum(1 for r in result if not r.get("success"))

            self._send_response(
                {
                    "id": "event",
                    "result": {
                        "type": "file_import_complete",
                        "data": {
                            "success": True,
                            "imported": success_count,
                            "failed": fail_count + len(skipped),
                            "skipped": skipped,
                        },
                    },
                }
            )
        except Exception as e:
            logger.warning(f"[ERROR] file_import: {e}\n{traceback.format_exc()}")
            self._send_response({"id": "event", "result": {"type": "file_import_error", "error": str(e)}})

    def _start_file_conversion(self, params):
        ai_assist = params.get("ai_assist", False)
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err

        if not self._start_task(
            "file_conversion",
            self._do_file_conversion,
            args=(workspace, ai_assist),
            kind="conversion",
            label="File conversion",
        ):
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
            self._send_response({"id": "event", "result": {"type": "file_conversion_complete", "data": result}})
        except Exception as e:
            logger.warning(f"[ERROR] file_conversion: {e}\n{traceback.format_exc()}")
            self._send_response({"id": "event", "result": {"type": "file_conversion_error", "error": str(e)}})

    def _auto_convert_pending(self, _params=None):
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "pending": 0, "converted": 0}

        supported = set(FileConverterManager.get_supported_formats())
        ws = Path(workspace)
        ws / RAW_FOLDER

        pending = []
        for f in ws.rglob("*"):
            if not f.is_file() or f.name.startswith("."):
                continue
            rel = f.relative_to(ws)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if RAW_FOLDER in rel.parts:
                continue
            if f.suffix.lower() in supported:
                pending.append(str(f))

        if not pending:
            return {"success": True, "pending": 0, "converted": 0}

        if not self._start_task(
            "auto_convert",
            self._do_auto_convert,
            args=(workspace, pending),
            kind="conversion",
            label="Auto convert",
        ):
            return {"success": False, "pending": len(pending), "converted": 0, "message": "转换任务正在进行中"}

        return {"success": True, "pending": len(pending), "converted": 0}

    def _do_auto_convert(self, workspace, pending_files):
        try:
            raw_path = str(Path(workspace) / "Raw")
            output_path = str(Path(workspace) / NOTES_FOLDER)
            results = self.file_converter.convert_batch(pending_files, output_path, raw_path=raw_path)
            from sidecar.convert_failures import record_convert_batch_results

            record_convert_batch_results(results)
            converted = sum(1 for r in results if r.get("success"))
            failed = sum(1 for r in results if not r.get("success"))
            self._send_response(
                {
                    "id": "event",
                    "result": {
                        "type": "auto_convert_complete",
                        "data": {
                            "total": len(pending_files),
                            "converted": converted,
                            "failed": failed,
                        },
                    },
                }
            )
        except Exception as e:
            logger.warning(f"[ERROR] auto_convert: {e}\n{traceback.format_exc()}")
            self._send_response({"id": "event", "result": {"type": "auto_convert_error", "error": str(e)}})

    def _retry_convert_file(self, params):
        file_path = (params.get("file") or params.get("path") or "").strip()
        workspace = self.config.workspace_path
        if not workspace or not file_path:
            return {"success": False, "message": "参数缺失"}
        if not self._start_task(
            f"convert_retry_{Path(file_path).stem}", self._do_retry_convert, args=(file_path, workspace)
        ):
            return {"success": False, "message": "转换任务正在进行中"}
        return {"success": True, "message": f"已开始重试转换：{file_path}"}

    def _do_retry_convert(self, file_path: str, workspace: str) -> None:
        ws = Path(workspace)
        full = ws / file_path if not Path(file_path).is_absolute() else Path(file_path)
        if not full.exists():
            record_convert_batch_results([{"success": False, "source": file_path, "error": "文件不存在"}])
            return
        raw_path = str(ws / RAW_FOLDER)
        output_path = str(ws / NOTES_FOLDER)
        results = self.file_converter.convert_batch([str(full)], output_path, raw_path=raw_path)
        record_convert_batch_results(results)

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
        output_path = str(ws / NOTES_FOLDER)
        results = self.file_converter.convert_batch(paths, output_path, raw_path=raw_path)
        record_convert_batch_results(results)

    def _dismiss_convert_failure(self, params):
        file_path = (params.get("file") or params.get("path") or "").strip()
        if not file_path:
            return {"success": False, "message": "缺少文件路径"}
        clear_convert_failure(file_path)
        return {"success": True, "message": f"已忽略：{file_path}"}

    def _extract_topics(self, params):
        topic_count = params.get("topic_count", None)
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err

        result = self.topic_extractor.extract_topics(specified_topic_count=topic_count)
        if not result.get("success"):
            return {"success": False, "message": result.get("error", "提取主题失败")}
        return result

    def _start_note_integration(self, params):
        auto_topic = params.get("auto_topic", True)
        topics = params.get("topics", [])
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err

        self._note_integration = NoteIntegration()

        if not self._start_task(
            "note_integration",
            self._do_note_integration,
            args=(workspace, auto_topic, topics),
            kind="ingest",
            label="Note integration",
        ):
            return {"success": False, "message": "整合任务正在进行中，请稍后"}

        return {"success": True, "message": "整合已开始"}

    def _do_note_integration(self, workspace, auto_topic, topics):
        _ = auto_topic
        ni = getattr(self, "_note_integration", None)
        if ni is None:
            ni = NoteIntegration()
            self._note_integration = ni
        try:
            documents = ni.load_documents_from_folder(workspace)
            result = ni.integrate(documents=documents, save_path=workspace, user_topics=topics if topics else None)
            ni.documents = []
            self._send_response({"id": "event", "result": {"type": "note_integration_complete", "data": result}})
        except Exception as e:
            if ni:
                ni.documents = []
            logger.warning(f"[ERROR] note_integration: {e}\n{traceback.format_exc()}")
            self._send_response({"id": "event", "result": {"type": "note_integration_error", "error": str(e)}})

    def _import_rss_feed(self, params):
        from sidecar.multi_source import import_rss_feed

        url = params.get("feed_url", "") or params.get("url", "")
        max_items = int(params.get("max_items", 10) or 10)
        fetch_articles = bool(params.get("fetch_articles", True))
        _, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
        return self._run_sync_job(
            "rss_import",
            kind="ingest",
            label="RSS import",
            message="正在手动导入 RSS",
            metadata={"experimental": True, "url": url},
            fn=lambda: import_rss_feed(url, max_items=max_items, fetch_articles=fetch_articles),
            complete_message=lambda result: f"RSS 导入完成: {result.get('imported', 0)} 条",
            complete_metadata=lambda result: {"imported": result.get("imported", 0)},
        )

    def _import_transcript(self, params):
        from sidecar.multi_source import import_transcript

        _, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
        return import_transcript(
            params.get("title", ""),
            params.get("content", ""),
            source=params.get("source", ""),
            speakers=params.get("speakers", ""),
        )

    # ── RSS Subscription Management ──

    def _save_rss_subscription(self, params):
        url = params.get("url", "")
        name = params.get("name", "")
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "缺少工作区"}
        from sidecar.multi_source import save_subscription

        return save_subscription(workspace, url, name)

    def _remove_rss_subscription(self, params):
        url = params.get("url", "")
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "message": "缺少工作区"}
        from sidecar.multi_source import remove_subscription

        return remove_subscription(workspace, url)

    def _list_rss_subscriptions(self, _params):
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": False, "subscriptions": []}
        from sidecar.multi_source import load_subscriptions

        return {"success": True, "subscriptions": load_subscriptions(workspace)}

    def _fetch_all_rss(self, _params):
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
        from sidecar.multi_source import fetch_all_subscriptions

        def imported_count(result):
            total = 0
            for item in result.get("results", []) if isinstance(result, dict) else []:
                total += int(item.get("imported") or 0)
            return total

        return self._run_sync_job(
            "rss_fetch_all",
            kind="ingest",
            label="RSS manual fetch",
            message="正在手动拉取 RSS 订阅",
            metadata={"experimental": True},
            fn=lambda: fetch_all_subscriptions(workspace),
            complete_message=lambda result: f"RSS 手动拉取完成: {imported_count(result)} 条",
            complete_metadata=lambda result: {"imported": imported_count(result)},
        )

    # ── Folder Watching ──

    def _list_watched_folders(self, _params):
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
        from modules.folder_watcher import load_watched_folders

        return {"success": True, "folders": load_watched_folders(workspace)}

    def _add_watched_folder(self, params):
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
        from modules.folder_watcher import add_watched_folder

        result = add_watched_folder(workspace, params.get("path", ""), bool(params.get("recursive", True)))
        if result.get("success"):
            self._server._restart_folder_monitor()
        return result

    def _remove_watched_folder(self, params):
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
        from modules.folder_watcher import remove_watched_folder

        result = remove_watched_folder(workspace, params.get("path", ""))
        if result.get("success"):
            self._server._restart_folder_monitor()
        return result

    def _scan_watched_folder(self, params):
        """立即扫描指定目录（缺省扫描全部已监控目录），新文件自动入库。"""
        workspace, err = self._require_workspace(message="请先设置工作区")
        if err:
            return err
        from modules.folder_watcher import collect_ingestible_files, load_watched_folders

        path = (params.get("path") or "").strip()
        recursive = bool(params.get("recursive", True))
        if path:
            folders = [{"path": path, "recursive": recursive}]
        else:
            folders = load_watched_folders(workspace)

        files: list[str] = []
        for f in folders:
            files.extend(collect_ingestible_files(str(f.get("path", "") or ""), bool(f.get("recursive", True))))
        files = sorted(set(files))
        if not files:
            return {"success": True, "scanned": 0, "message": "未发现可导入文件"}
        if not self._start_task(
            "folder_scan",
            self._do_folder_scan,
            args=(files,),
            kind="ingest",
            label="Folder scan",
        ):
            return {"success": False, "message": "扫描任务正在进行中"}
        return {"success": True, "scanned": len(files), "message": f"发现 {len(files)} 个文件，正在导入"}

    def _do_folder_scan(self, files: list[str]) -> None:
        self._server._handle_watched_folder_files(files)
