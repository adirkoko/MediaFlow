import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.infrastructure.jobs_store import JobsStore
from app.services.job_manager import JobManager

log = logging.getLogger("worker")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Worker:
    def __init__(self, manager: JobManager) -> None:
        self._manager = manager
        self._store = JobsStore()
        self._semaphore = asyncio.Semaphore(settings.max_parallel_jobs)

    async def run_forever(self) -> None:
        log.info("Worker started (max_parallel_jobs=%s)", settings.max_parallel_jobs)
        while True:
            enq = await self._manager.queue.get()
            asyncio.create_task(self._handle_job(enq.job_id))

    async def _handle_job(self, job_id: str) -> None:
        async with self._semaphore:
            job = self._store.get_job(job_id)
            if not job:
                log.warning("Job not found: %s", job_id)
                return

            log.info("Starting job %s for user=%s", job_id, job.user)
            self._store.update_status(job_id, "running", started_at=_utc_now())

            try:
                # Stub processing: simulate work + generate an output file.
                await asyncio.sleep(3)

                out_dir = Path(settings.outputs_dir) / job_id
                out_dir.mkdir(parents=True, exist_ok=True)

                # For now: create a simple result file. Later we will generate mp3/mp4.
                result_path = out_dir / "result.txt"
                result_path.write_text(
                    f"job_id={job_id}\nuser={job.user}\nurl={job.url}\nmode={job.mode}\nquality={job.quality}\n",
                    encoding="utf-8",
                )

                self._store.update_status(job_id, "succeeded", finished_at=_utc_now())
                log.info("Job %s succeeded", job_id)

            except Exception as e:
                log.exception("Job %s failed", job_id)
                self._store.update_status(job_id, "failed", finished_at=_utc_now(), error_message=str(e))
