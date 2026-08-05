from sidecar import job_status
from sidecar.handlers.base import BaseHandler


class JobHandler(BaseHandler):
    def register_routes(self, router):
        router.register("get_jobs", self._get_jobs)

    def _get_jobs(self, params):
        include_finished = params.get("include_finished", True)
        limit = params.get("limit", 50)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 50
        return {
            "success": True,
            "jobs": job_status.list_jobs(include_finished=bool(include_finished), limit=limit),
        }
