import asyncio
import logging
import time
from app.infrastructure.usage_store import UsageStore
from datetime import datetime, timezone
from pathlib import Path
from app.core.config import settings
from app.infrastructure.jobs_store import JobsStore
from app.services.job_manager import JobManager
from app.services.youtube_processor import YouTubeProcessor

log = logging.getLogger("worker")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Worker:
    def __init__(self, manager: JobManager) -> None:
        self._manager = manager
        self._store = JobsStore()
        self._semaphore = asyncio.Semaphore(settings.max_parallel_jobs)
        self._processor = YouTubeProcessor()
        self._usage = UsageStore()

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

            out_dir = Path(settings.outputs_dir) / job_id
            out_dir.mkdir(parents=True, exist_ok=True)
            job_log = out_dir / "job.log"

            def _append_log(line: str) -> None:
                job_log.write_text(
                    (job_log.read_text(encoding="utf-8") if job_log.exists() else "")
                    + line
                    + "\n",
                    encoding="utf-8",
                )

            log.info("Starting job %s for user=%s", job_id, job.user)
            self._store.update_status(job_id, "running", started_at=_utc_now())
            _append_log(
                f"START {job_id} user={job.user} mode={job.mode} quality={job.quality}"
            )
            _append_log(f"url={job.url}")
            t0 = time.perf_counter()

            try:
                # Run blocking processing in a thread to avoid blocking the event loop
                result = await asyncio.to_thread(
                    self._processor.process,
                    job_id,
                    job.url,
                    job.mode,
                    job.quality,
                )

                duration_ms = int((time.perf_counter() - t0) * 1000)
                _append_log(f"OUTPUT={result.output_path.name}")
                self._store.update_status(
                    job_id,
                    "succeeded",
                    finished_at=_utc_now(),
                    output_filename=result.output_path.name,
                    output_type=result.output_type,
                )

                self._usage.add_event(
                    user=job.user,
                    mode=job.mode,
                    is_playlist=result.is_playlist,
                    duration_ms=duration_ms,
                    success=True,
                    created_at=_utc_now(),
                )

                log.info("Job %s succeeded", job_id)

            except Exception as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                log.exception("Job %s failed", job_id)
                _append_log(f"ERROR={type(e).__name__}: {e}")

                self._store.update_status(
                    job_id, "failed", finished_at=_utc_now(), error_message=str(e)
                )

                self._usage.add_event(
                    user=job.user,
                    mode=job.mode,
                    is_playlist=False, # Default to False on early failure
                    duration_ms=duration_ms,
                    success=False,
                    created_at=_utc_now(),
                )
