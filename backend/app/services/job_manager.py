import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import settings
from app.infrastructure.jobs_store import JobsStore


@dataclass(frozen=True)
class EnqueuedJob:
    job_id: str


class JobManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[EnqueuedJob] = asyncio.Queue(maxsize=settings.queue_max_size)
        self._store = JobsStore()

    @property
    def queue(self) -> asyncio.Queue[EnqueuedJob]:
        return self._queue

    def create_job(self, user: str, url: str, mode: str, quality: str) -> str:
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
        return job_id

    async def enqueue(self, job_id: str) -> None:
        await self._queue.put(EnqueuedJob(job_id=job_id))
