from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from app.infrastructure.jobs_store import JobsStore

log = logging.getLogger("startup_reconciliation")


@dataclass(frozen=True)
class ReconcileResult:
    updated: int
    queued: int
    running: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reconcile_active_jobs_on_startup() -> ReconcileResult:
    """
    Mark stale in-flight jobs as failed after process restart.

    Jobs with status queued/running are in-memory execution state dependent.
    After a server restart, they are no longer actually processing.
    """
    store = JobsStore()
    active = store.list_active_jobs(limit=20000)
    if not active:
        return ReconcileResult(updated=0, queued=0, running=0)

    now = _utc_now()
    queued = 0
    running = 0

    for job in active:
        if job.status == "queued":
            queued += 1
        elif job.status == "running":
            running += 1

        store.update_progress(
            job.job_id,
            None,
            "failed (server restart)",
            updated_at=now,
            eta_seconds=None,
            speed_bps=None,
        )
        store.update_status(
            job.job_id,
            "failed",
            finished_at=now,
            error_message="Job interrupted by server restart",
            error_code="SERVER_RESTART",
        )

    result = ReconcileResult(updated=len(active), queued=queued, running=running)
    log.warning(
        "Startup reconciliation applied: failed %s stale jobs (queued=%s running=%s)",
        result.updated,
        result.queued,
        result.running,
    )
    return result
