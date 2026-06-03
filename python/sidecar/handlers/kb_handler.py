"""Knowledge base utilities: lint, chat archive, cascade queue."""

from sidecar.archive_wiki import archive_chat_answer
from sidecar.cascade_runner import (
    clear_cascade_failure,
    load_cascade_failures,
    retry_failed_cascades,
)
from sidecar.handlers.base import BaseHandler
from sidecar.kb_lint import load_lint_report, log_lint_report, run_kb_lint
from sidecar.survey_append import append_chat_to_survey


class KbHandler(BaseHandler):
    def register_routes(self, router) -> None:
        router.register("run_kb_lint", self._run_kb_lint)
        router.register("get_lint_report", self._get_lint_report)
        router.register("archive_chat_answer", self._archive_chat_answer)
        router.register("append_chat_to_survey", self._append_chat_to_survey)
        router.register("get_cascade_failures", self._get_cascade_failures)
        router.register("retry_cascade_topic", self._retry_cascade_topic)
        router.register("retry_all_cascade_failures", self._retry_all_cascade_failures)
        router.register("dismiss_cascade_failure", self._dismiss_cascade_failure)

    def _run_kb_lint(self, _params):
        report = run_kb_lint(send_response=self._send_response)
        log_lint_report(report)
        return report

    def _get_lint_report(self, _params):
        return load_lint_report()

    def _archive_chat_answer(self, params):
        return archive_chat_answer(
            question=params.get("question", ""),
            answer=params.get("answer", ""),
            topic=params.get("topic", ""),
            title=params.get("title", ""),
            target=params.get("target", "note"),
            context_file=params.get("context_file", ""),
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
