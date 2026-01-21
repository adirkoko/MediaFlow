import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.infrastructure.jobs_store import JobsStore
from app.infrastructure.usage_store import UsageStore
from app.services.job_manager import JobManager
from app.services.youtube_processor import YouTubeProcessor
from app.services.backoff import BackoffConfig, run_with_backoff
from app.services.cookies import prepare_job_cookies

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
        """Main loop that listens to the queue and spawns job tasks."""
        log.info("Worker started (max_parallel_jobs=%s)", settings.max_parallel_jobs)
        while True:
            enq = await self._manager.queue.get()
            asyncio.create_task(self._handle_job(enq.job_id))

    async def _handle_job(self, job_id: str) -> None:
        """Handles a single job execution with concurrency control and error handling."""
        async with self._semaphore:
            job = self._store.get_job(job_id)
            if not job:
                log.warning("Job not found: %s", job_id)
                return

            # Prepare job directory and local logging
            out_dir = Path(settings.outputs_dir) / job_id
            out_dir.mkdir(parents=True, exist_ok=True)
            job_log = out_dir / "job.log"

            def _append_log(line: str) -> None:
                """Appends a line of text to the job-specific log file."""
                job_log.write_text(
                    (job_log.read_text(encoding="utf-8") if job_log.exists() else "")
                    + line
                    + "\n",
                    encoding="utf-8",
                )

            def progress_cb(pct: int | None, stage: str, eta_seconds: int | None, speed_bps: int | None) -> None:
                self._store.update_progress(
                    job_id,
                    pct,
                    stage,
                    updated_at=_utc_now(),
                    eta_seconds=eta_seconds,
                    speed_bps=speed_bps,
                )

            log.info("Starting job %s for user=%s", job_id, job.user)
            self._store.update_status(job_id, "running", started_at=_utc_now())
            self._store.update_progress(job_id, 0, "starting", updated_at=_utc_now(), eta_seconds=None, speed_bps=None)

            _append_log(
                f"START {job_id} user={job.user} mode={job.mode} quality={job.quality}"
            )
            _append_log(f"url={job.url}")

            t0 = time.perf_counter()

            # Create a temporary cookie context for this job to prevent file locking/leaks
            cookies_handle = prepare_job_cookies(settings.cookies_file, job_id)

            try:
                # Initialize exponential backoff configuration from settings
                cfg = BackoffConfig(
                    max_attempts=settings.max_attempts,
                    base_delay_seconds=settings.backoff_base_seconds,
                )

                def _run():
                    """Blocking operation to be executed within the thread pool."""
                    return self._processor.process(
                        job_id=job_id,
                        url=job.url,
                        mode=job.mode,
                        quality=job.quality,
                        # Pass the unique cookie file path to the processor
                        cookies_path=(str(cookies_handle.path) if cookies_handle else None),
                        progress_cb=progress_cb,
                    )

                # Execute processor in a thread to keep the event loop responsive
                result = await asyncio.to_thread(lambda: run_with_backoff(_run, cfg))

                duration_ms = int((time.perf_counter() - t0) * 1000)
                _append_log(f"OUTPUT={result.output_path.name}")
                self._store.update_progress(job_id, 100, "done", updated_at=_utc_now(), eta_seconds=0, speed_bps=0)

                # Update status and clean error code on success
                self._store.update_status(
                    job_id,
                    "succeeded",
                    finished_at=_utc_now(),
                    output_filename=result.output_path.name,
                    output_type=result.output_type,
                    error_code=None,
                )

                # Log successful usage event
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

                # Classify exception for frontend-friendly error reporting
                error_code = self._classify_error(e)
                self._store.update_progress(job_id, None, "failed", updated_at=_utc_now(), eta_seconds=None, speed_bps=None)
                self._store.update_status(
                    job_id,
                    "failed",
                    finished_at=_utc_now(),
                    error_message=str(e),
                    error_code=error_code,
                )

                self._usage.add_event(
                    user=job.user,
                    mode=job.mode,
                    is_playlist=False,
                    duration_ms=duration_ms,
                    success=False,
                    created_at=_utc_now(),
                )

            finally:
                # Always clean up the temporary cookie file
                if cookies_handle:
                    cookies_handle.cleanup()

    def _classify_error(self, exc: Exception) -> str:
        """Classifies downstream exceptions into standardized error codes."""
        msg = str(exc).lower()

        if "ffmpeg" in msg and ("not found" in msg or "no such file" in msg):
            return "FFMPEG_MISSING"
        if "http error 429" in msg or "too many requests" in msg:
            return "RATE_LIMITED"
        if "sign in" in msg or "login" in msg or "cookies" in msg:
            return "AUTH_REQUIRED"
        if "requested format is not available" in msg or "format not available" in msg:
            return "FORMAT_UNAVAILABLE"
        if "timed out" in msg or "timeout" in msg or "temporary failure" in msg:
            return "NETWORK"
        return "UPSTREAM_ERROR"
