from types import SimpleNamespace

from sidecar import job_status
from sidecar.handlers.job_handler import JobHandler


def setup_function():
    job_status.clear_jobs()


def test_job_lifecycle_emits_and_lists() -> None:
    events = []

    def send_event(resp: dict) -> None:
        events.append(resp)

    job_status.start_job("ingest_pipeline", kind="ingest", label="Ingest", send_event=send_event)
    job_status.update_job("ingest_pipeline", progress=0.5, message="分类中", send_event=send_event)
    job_status.complete_job("ingest_pipeline", message="完成", send_event=send_event)

    job = job_status.get_job("ingest_pipeline")
    assert job is not None
    assert job["status"] == "complete"
    assert job["progress"] == 1.0
    assert job["finished_at"] is not None
    assert len(job_status.list_jobs()) == 1
    assert [e["result"]["type"] for e in events] == ["job_update", "job_update", "job_update"]


def test_job_handler_returns_jobs() -> None:
    job_status.start_job("cli_agent", kind="cli_agent")
    handler = JobHandler(SimpleNamespace(_ctx=SimpleNamespace(config=None, logger=None)))

    listed = handler._get_jobs({"include_finished": True})
    assert listed["success"] is True
    assert listed["jobs"][0]["id"] == "cli_agent"
