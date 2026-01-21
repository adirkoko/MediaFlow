from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.core.deps import get_current_username
from app.core.config import settings
from app.infrastructure.jobs_store import JobsStore
from app.models.schemas import CreateJobRequest, CreateJobResponse, JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=CreateJobResponse)
async def create_job(
    payload: CreateJobRequest,
    username: str = Depends(get_current_username),
) -> CreateJobResponse:
    # Lazy import to avoid circular dependency; manager is attached to app.state in main.py
    from app.main import get_manager  # noqa

    manager = get_manager()
    job_id = manager.create_job(user=username, url=payload.url, mode=payload.mode.value, quality=payload.quality)
    await manager.enqueue(job_id)

    return CreateJobResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, username: str = Depends(get_current_username)) -> JobResponse:
    store = JobsStore()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user != username:
        raise HTTPException(status_code=403, detail="Forbidden")

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
    )


@router.get("/{job_id}/download")
def download(job_id: str, username: str = Depends(get_current_username)):
    store = JobsStore()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user != username:
        raise HTTPException(status_code=403, detail="Forbidden")
    if job.status != "succeeded":
        raise HTTPException(status_code=409, detail=f"Job not ready (status={job.status})")

    result_path = Path(settings.outputs_dir) / job_id / "result.txt"
    if not result_path.exists():
        raise HTTPException(status_code=500, detail="Output missing")

    return FileResponse(path=str(result_path), filename=f"{job_id}.txt")
