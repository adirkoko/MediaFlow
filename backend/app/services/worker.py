import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.infrastructure.jobs_store import JobsStore
from app.infrastructure.usage_store import UsageStore
from app.services.backoff import BackoffConfig, run_with_backoff
from app.services.cookies import prepare_job_cookies
from app.services.error_codes import classify_error, is_retryable_error
from app.services.job_logging import JobLogger
from app.services.job_manager import JobManager
from app.services.youtube_processor import YouTubeProcessor
from app.core.exceptions import AllPlaylistItemsFailed, JobCanceled

log = logging.getLogger("worker")


def _utc_now() -> str:
    # Single source of UTC timestamps for DB fields / job progress updates.
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
                self._manager.release_cancel_event(job_id)
                log.warning("Job not found: %s", job_id)
                return
            if job.status != "queued":
                self._manager.release_cancel_event(job_id)
                log.info("Skipping job %s with status=%s", job_id, job.status)
                return

            cancel_event = self._manager.bind_cancel_event(job_id)

            def should_cancel() -> bool:
                return cancel_event.is_set()

            # Prepare job directory and per-job logger.
            out_dir = Path(settings.outputs_dir) / job_id
            out_dir.mkdir(parents=True, exist_ok=True)
            job_log = JobLogger(out_dir / "job.log")

            def progress_cb(
                pct: int | None,
                stage: str,
                eta_seconds: int | None,
                speed_bps: int | None,
            ) -> None:
                if should_cancel():
                    raise JobCanceled("Job canceled by user")
                # Persist progress for polling + SSE.
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
            self._store.update_progress(
                job_id,
                0,
                "starting",
                updated_at=_utc_now(),
                eta_seconds=None,
                speed_bps=None,
            )

            job_log.log(
                f"START {job_id} user={job.user} mode={job.mode} quality={job.quality}"
            )
            job_log.log(f"url={job.url}")

            t0 = time.perf_counter()

            # Create a temporary cookie context for this job to prevent file locking/leaks.
            cookies_handle = prepare_job_cookies(settings.cookies_file, job_id)

            try:
                if should_cancel():
                    raise JobCanceled("Job canceled by user")

                # Initialize exponential backoff configuration from settings.
                cfg = BackoffConfig(
                    max_attempts=settings.max_attempts,
                    base_delay_seconds=settings.backoff_base_seconds,
                )

                def _run():
                    """Blocking operation executed in a thread to keep the event loop responsive."""
                    return self._processor.process(
                        job_id=job_id,
                        url=job.url,
                        mode=job.mode,
                        quality=job.quality,
                        # Pass the per-job cookie file path to the processor.
                        cookies_path=(
                            str(cookies_handle.path) if cookies_handle else None
                        ),
                        progress_cb=progress_cb,
                        should_cancel=should_cancel,
                    )

                # Execute processor in a thread; wrap with backoff for transient failures.
                result = await asyncio.to_thread(
                    lambda: run_with_backoff(
                        _run,
                        cfg,
                        should_retry=is_retryable_error,
                    )
                )

                if should_cancel():
                    raise JobCanceled("Job canceled by user")

                duration_ms = int((time.perf_counter() - t0) * 1000)
                job_log.log(f"OUTPUT={result.output_path.name}")

                self._store.update_progress(
                    job_id,
                    100,
                    "done",
                    updated_at=_utc_now(),
                    eta_seconds=0,
                    speed_bps=0,
                )
                if should_cancel():
                    raise JobCanceled("Job canceled by user")

                # Mark the job as succeeded and store output metadata.
                self._store.update_status(
                    job_id,
                    "succeeded",
                    finished_at=_utc_now(),
                    output_filename=result.output_path.name,
                    output_type=result.output_type,
                    error_code=None,
                    playlist_total=result.playlist_total,
                    playlist_succeeded=result.playlist_succeeded,
                    playlist_failed=result.playlist_failed,
                )

                # Usage metrics (operational visibility).
                self._usage.add_event(
                    user=job.user,
                    mode=job.mode,
                    is_playlist=result.is_playlist,
                    duration_ms=duration_ms,
                    success=True,
                    created_at=_utc_now(),
                )

                log.info("Job %s succeeded", job_id)

            except JobCanceled as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                log.info("Job %s canceled by user", job_id)
                job_log.log(f"CANCELED={e}")

                self._store.update_progress(
                    job_id,
                    None,
                    "canceled",
                    updated_at=_utc_now(),
                    eta_seconds=None,
                    speed_bps=None,
                )
                self._store.update_status(
                    job_id,
                    "canceled",
                    finished_at=_utc_now(),
                    error_message=str(e),
                    error_code="CANCELED",
                )

                is_playlist = "list=" in (job.url or "").lower()
                self._usage.add_event(
                    user=job.user,
                    mode=job.mode,
                    is_playlist=is_playlist,
                    duration_ms=duration_ms,
                    success=False,
                    created_at=_utc_now(),
                )

            except Exception as e:
                duration_ms = int((time.perf_counter() - t0) * 1000)

                log.exception("Job %s failed", job_id)
                job_log.log(f"ERROR={type(e).__name__}: {e}")

                error_code = classify_error(e)
                is_playlist = "list=" in (job.url or "").lower()

                p_total, p_succeeded, p_failed = None, None, None
                if isinstance(e, AllPlaylistItemsFailed):
                    p_total = e.total
                    p_succeeded = 0
                    p_failed = e.failed

                self._store.update_progress(
                    job_id,
                    None,
                    "failed",
                    updated_at=_utc_now(),
                    eta_seconds=None,
                    speed_bps=None,
                )
                self._store.update_status(
                    job_id,
                    "failed",
                    finished_at=_utc_now(),
                    error_message=str(e),
                    error_code=error_code,
                    playlist_total=p_total,
                    playlist_succeeded=p_succeeded,
                    playlist_failed=p_failed,
                )

                self._usage.add_event(
                    user=job.user,
                    mode=job.mode,
                    is_playlist=is_playlist,
                    duration_ms=duration_ms,
                    success=False,
                    created_at=_utc_now(),
                )

            finally:
                # Always clean up the temporary cookie file.
                if cookies_handle:
                    cookies_handle.cleanup()
                self._manager.release_cancel_event(job_id)
