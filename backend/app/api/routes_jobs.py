from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.core.exceptions import QuotaExceeded
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
    # Lazy import to avoid circular dependency
    from app.main import get_manager  # noqa

    manager = get_manager()

    try:
        # manager.create_job returns a tuple: (job_id, reused)
        job_id, reused = manager.create_job(
            user=username,
            url=payload.url,
            mode=payload.mode.value,
            quality=payload.quality,
        )
    except QuotaExceeded as e:
        # 429 status is appropriate for Quota/Rate limits
        raise HTTPException(status_code=429, detail=str(e))

    # Only enqueue if it's a fresh job, not a reused one
    if not reused:
        await manager.enqueue(job_id)

    return CreateJobResponse(job_id=job_id, status="queued", reused=reused)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, username: str = Depends(get_current_username)) -> JobResponse:
    store = JobsStore()
    job = store.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user != username:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Injected 'error_code' so UI can distinguish between rate-limits, auth, or network errors
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
        error_code=job.error_code,  # <--- Added this line
        output_filename=job.output_filename,
        output_type=job.output_type,
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
        raise HTTPException(
            status_code=409, detail=f"Job not ready (status={job.status})"
        )

    out_dir = Path(settings.outputs_dir) / job_id
    if not out_dir.exists():
        raise HTTPException(status_code=500, detail="Output missing")

    # 1. Use the deterministic filename stored in the DB if available
    if job.output_filename:
        p = out_dir / job.output_filename
        if p.exists():
            return FileResponse(path=str(p), filename=p.name)

    # 2. Check for common result names (if DB record is empty)
    candidates = ["result.mp3", "result.mp4", "result.mkv", "result.webm", "result.zip"]
    for name in candidates:
        p = out_dir / name
        if p.exists():
            return FileResponse(path=str(p), filename=p.name)

    # 3. Last resort: Return the first relevant file in directory
    valid_extensions = {".mp3", ".mp4", ".mkv", ".webm", ".zip"}
    for p in out_dir.iterdir():
        if p.is_file() and p.suffix.lower() in valid_extensions:
            return FileResponse(path=str(p), filename=p.name)

    raise HTTPException(status_code=500, detail="No downloadable output found")
