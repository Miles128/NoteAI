"""Knowledge base utilities: lint and chat archive."""

from sidecar.archive_wiki import archive_chat_answer
from sidecar.handlers.base import BaseHandler
from sidecar.kb_lint import run_kb_lint


class KbHandler(BaseHandler):
    def register_routes(self, router) -> None:
        router.register("run_kb_lint", self._run_kb_lint)
        router.register("archive_chat_answer", self._archive_chat_answer)

    def _run_kb_lint(self, _params):
        return run_kb_lint()

    def _archive_chat_answer(self, params):
        return archive_chat_answer(
            question=params.get("question", ""),
            answer=params.get("answer", ""),
            topic=params.get("topic", ""),
            title=params.get("title", ""),
        )
