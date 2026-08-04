"""Knowledge base utilities: lint, chat archive, cascade queue."""

from sidecar.archive_wiki import archive_chat_answer
from sidecar.cascade_runner import (
    clear_cascade_failure,
    load_cascade_failures,
    retry_failed_cascades,
)
from sidecar.dashboard_status import get_dashboard_status
from sidecar.duplicate_review import get_duplicate_review, merge_duplicate_notes, merge_note_group
from sidecar.handlers.base import BaseHandler
from sidecar.kb_lint import load_lint_report, log_lint_report, run_kb_lint
from sidecar.survey_append import append_chat_to_survey


class KbHandler(BaseHandler):
    def register_routes(self, router) -> None:
        router.register("get_dashboard_status", self._get_dashboard_status)
        router.register("run_kb_lint", self._run_kb_lint)
        router.register("get_lint_report", self._get_lint_report)
        router.register("get_duplicate_review", self._get_duplicate_review)
        router.register("merge_duplicate_notes", self._merge_duplicate_notes)
        router.register("merge_note_group", self._merge_note_group)
        router.register("get_chunk_merge_candidates", self._get_chunk_merge_candidates)
        router.register("scan_merge_candidates", self._scan_merge_candidates)
        router.register("archive_chat_answer", self._archive_chat_answer)
        router.register("append_chat_to_survey", self._append_chat_to_survey)
        router.register("get_cascade_failures", self._get_cascade_failures)
        router.register("retry_cascade_topic", self._retry_cascade_topic)
        router.register("retry_all_cascade_failures", self._retry_all_cascade_failures)
        router.register("dismiss_cascade_failure", self._dismiss_cascade_failure)

    def _get_dashboard_status(self, _params):
        workspace, err = self._require_workspace()
        if err:
            return err
        topics_handler = getattr(self._server, "_topics_handler", None)
        if topics_handler is not None:
            topics_handler.schedule_pending_maintenance()
        return get_dashboard_status(workspace)

    def _run_kb_lint(self, _params):
        report = run_kb_lint(send_response=self._send_response)
        log_lint_report(report)
        return report

    def _get_lint_report(self, _params):
        return load_lint_report()

    def _get_duplicate_review(self, params):
        workspace, err = self._require_workspace()
        if err:
            return err
        try:
            return get_duplicate_review(
                workspace,
                (params.get("file_path") or "").strip(),
                (params.get("related_file") or "").strip(),
            )
        except (OSError, ValueError) as exc:
            return {"success": False, "message": str(exc)}

    def _merge_duplicate_notes(self, params):
        workspace, err = self._require_workspace()
        if err:
            return err
        try:
            return merge_duplicate_notes(
                workspace,
                (params.get("file_path") or "").strip(),
                (params.get("related_file") or "").strip(),
                (params.get("title") or "").strip(),
            )
        except (OSError, ValueError) as exc:
            return {"success": False, "message": str(exc)}

    def _merge_note_group(self, params):
        workspace, err = self._require_workspace()
        if err:
            return err
        try:
            return merge_note_group(
                workspace,
                [str(path) for path in (params.get("file_paths") or [])],
                str(params.get("title") or ""),
                delete_authorized=params.get("delete_authorized") is True,
            )
        except (OSError, ValueError) as exc:
            return {"success": False, "message": str(exc)}

    def _get_chunk_merge_candidates(self, _params):
        workspace = self.config.workspace_path
        if not workspace:
            return {"success": True, "items": []}
        from sidecar.chunk_similarity import load_chunk_similarity_graph

        graph = load_chunk_similarity_graph(workspace)
        return {"success": True, "items": graph.get("candidates") or [], "needs_build": not bool(graph)}

    def _scan_merge_candidates(self, _params):
        workspace, err = self._require_workspace()
        if err:
            return err
        from sidecar.chunk_similarity import build_chunk_similarity_graph

        return build_chunk_similarity_graph(workspace)

    def _archive_chat_answer(self, params):
        return archive_chat_answer(
            question=params.get("question", ""),
            answer=params.get("answer", ""),
            topic=params.get("topic", ""),
            title=params.get("title", ""),
            target=params.get("target", "note"),
            context_file=params.get("context_file", ""),
            citations=params.get("citations") or [],
            preview_only=params.get("preview_only") is True,
        )

    def _append_chat_to_survey(self, params):
        return append_chat_to_survey(
            question=params.get("question", ""),
            answer=params.get("answer", ""),
            topic=params.get("topic", ""),
            context_file=params.get("context_file", ""),
        )

    def _get_cascade_failures(self, _params):
        return {"success": True, "items": load_cascade_failures()}

    def _retry_cascade_topic(self, params):
        topic = (params.get("topic") or "").strip()
        if not topic:
            return {"success": False, "message": "缺少主题"}
        if not self._start_task(
            f"cascade_retry_{topic}",
            self._do_cascade_survey_update,
            args=(topic,),
        ):
            return {"success": False, "message": "综述任务已在运行"}
        return {"success": True, "message": f"已开始重试综述：{topic}"}

    def _retry_all_cascade_failures(self, _params):
        topics = [x.get("topic") for x in load_cascade_failures() if x.get("topic")]
        if not topics:
            return {"success": True, "message": "无失败项", "updated": 0}
        if not self._start_task("cascade_retry_all", self._retry_all_cascades_task):
            return {"success": False, "message": "综述任务已在运行"}
        return {"success": True, "message": f"已开始重试 {len(topics)} 个失败主题"}

    def _retry_all_cascades_task(self) -> None:
        retry_failed_cascades(send_response=self._send_response)

    def _dismiss_cascade_failure(self, params):
        topic = (params.get("topic") or "").strip()
        if not topic:
            return {"success": False, "message": "缺少主题"}
        clear_cascade_failure(topic)
        return {"success": True, "message": f"已忽略：{topic}"}
