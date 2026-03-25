# backend/app/services/job_manager.py
import asyncio
import uuid
import hashlib
import threading

from app.core.config import settings
from app.core.exceptions import QuotaExceeded
from dataclasses import dataclass
from datetime import datetime, timezone
from app.infrastructure.jobs_store import JobsStore


@dataclass(frozen=True)
class EnqueuedJob:
    job_id: str


class JobManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[EnqueuedJob] = asyncio.Queue(
            maxsize=settings.queue_max_size
        )
        self._store = JobsStore()
        self._cancel_lock = threading.Lock()
        self._cancel_events: dict[str, threading.Event] = {}
        self._pending_cancel: set[str] = set()

    @property
    def queue(self) -> asyncio.Queue[EnqueuedJob]:
        return self._queue

    def create_job(
        self, user: str, url: str, mode: str, quality: str
    ) -> tuple[str, bool]:
        # Quota check
        active = self._store.count_active_jobs_for_user(user)
        if active >= settings.max_active_jobs_per_user:
            raise QuotaExceeded(
                f"Too many active jobs (limit={settings.max_active_jobs_per_user})"
            )

        fp = self._fingerprint(user, url, mode, quality)

        # Dedup check
        dup = self._store.find_duplicate_active_job(
            user=user, fingerprint=fp, window_minutes=settings.dedup_window_minutes
        )
        if dup:
            return dup, True

        job_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        self._store.create_job(
            job_id=job_id,
            user=user,
            url=url,
            mode=mode,
            quality=quality,
            status="queued",
            created_at=created_at,
        )

        # Persist fingerprint immediately
        self._store.update_status(job_id, "queued", request_fingerprint=fp)

        return job_id, False

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(EnqueuedJob(job_id=job_id))

    def request_cancel(self, job_id: str) -> None:
        with self._cancel_lock:
            event = self._cancel_events.get(job_id)
            if event is not None:
                event.set()
                return
            self._pending_cancel.add(job_id)

    def bind_cancel_event(self, job_id: str) -> threading.Event:
        with self._cancel_lock:
            event = self._cancel_events.get(job_id)
            if event is None:
                event = threading.Event()
                self._cancel_events[job_id] = event
            if job_id in self._pending_cancel:
                event.set()
                self._pending_cancel.discard(job_id)
            return event

    def release_cancel_event(self, job_id: str) -> None:
        with self._cancel_lock:
            self._cancel_events.pop(job_id, None)
            self._pending_cancel.discard(job_id)

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._cancel_lock:
            event = self._cancel_events.get(job_id)
            if event is not None and event.is_set():
                return True
            return job_id in self._pending_cancel

    def _fingerprint(self, user: str, url: str, mode: str, quality: str) -> str:
        key = f"{user}|{url.strip()}|{mode}|{quality.strip().lower()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()
