from sidecar import job_status
from sidecar.handlers.base import BaseHandler


class JobHandler(BaseHandler):
    def register_routes(self, router):
        router.register("get_jobs", self._get_jobs)
        router.register("get_job", self._get_job)

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

    def _get_job(self, params):
        job_id = str(params.get("id") or params.get("job_id") or "").strip()
        if not job_id:
            return {"success": False, "message": "缺少 job id"}
        job = job_status.get_job(job_id)
        if not job:
            return {"success": False, "message": "任务不存在"}
        return {"success": True, "job": job}
