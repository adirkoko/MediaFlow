from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import require_admin
from app.infrastructure.audit_logs_repository import AuditLogsRepository
from app.infrastructure.jobs_store import JobRecord, JobsStore
from app.infrastructure.users_repository import UserRecord, UsersRepository
from app.models.schemas import CancelJobResponse, JobResponse
from app.services.usage_service import UsageService

router = APIRouter(prefix="/admin/jobs", tags=["admin-jobs"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_response(job: JobRecord) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        user=job.user,
        url=job.url,
        mode=job.mode,
        quality=job.quality,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_message=job.error_message,
        output_filename=job.output_filename,
        output_type=job.output_type,
        error_code=job.error_code,
        progress_percent=job.progress_percent,
        stage=job.stage,
        updated_at=job.updated_at,
        eta_seconds=job.eta_seconds,
        speed_bps=job.speed_bps,
        playlist_total=job.playlist_total,
        playlist_succeeded=job.playlist_succeeded,
        playlist_failed=job.playlist_failed,
    )


@router.get("", response_model=list[JobResponse])
def list_admin_jobs(
    user: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin_user: UserRecord = Depends(require_admin),
) -> list[JobResponse]:
    _ = admin_user
    jobs = JobsStore().list_jobs_admin(user=user, status=status, limit=limit, offset=offset)
    return [_job_response(job) for job in jobs]


@router.get("/{job_id}", response_model=JobResponse)
def get_admin_job(
    job_id: str,
    admin_user: UserRecord = Depends(require_admin),
) -> JobResponse:
    _ = admin_user
    job = JobsStore().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)


@router.post("/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_admin_job(
    job_id: str,
    admin_user: UserRecord = Depends(require_admin),
) -> CancelJobResponse:
    from app.main import get_manager  # noqa

    store = JobsStore()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    manager = get_manager()
    now = _utc_now()
    if job.status == "queued":
        manager.request_cancel(job_id)
        store.update_progress(job_id, None, "canceled", updated_at=now)
        store.update_status(
            job_id,
            "canceled",
            finished_at=now,
            error_message="Job canceled by admin",
            error_code="CANCELED",
        )
        user = UsersRepository().get_user_by_username(job.user)
        if user:
            UsageService().record_job_finished(
                user_id=user.id,
                job_id=job_id,
                event_type="job_canceled",
                mode=job.mode,
                quality=job.quality,
                error_code="CANCELED",
            )
        AuditLogsRepository().add_event(
            actor_user_id=admin_user.id,
            action="ADMIN_JOB_CANCELED",
            target_type="job",
            target_id=job_id,
            metadata={"previous_status": job.status, "user": job.user},
        )
        return CancelJobResponse(job_id=job_id, status="canceled", cancel_requested=True)

    if job.status == "running":
        manager.request_cancel(job_id)
        store.update_progress(job_id, None, "cancel requested by admin", updated_at=now)
        AuditLogsRepository().add_event(
            actor_user_id=admin_user.id,
            action="ADMIN_JOB_CANCEL_REQUESTED",
            target_type="job",
            target_id=job_id,
            metadata={"previous_status": job.status, "user": job.user},
        )
        return CancelJobResponse(job_id=job_id, status="running", cancel_requested=True)

    if job.status == "canceled":
        return CancelJobResponse(job_id=job_id, status="canceled", cancel_requested=False)

    raise HTTPException(status_code=409, detail=f"Cannot cancel job in status={job.status}")
