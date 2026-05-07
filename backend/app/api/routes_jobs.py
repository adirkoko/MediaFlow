# backend/app/api/routes_jobs.py
import asyncio
import json
import shutil
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from pathlib import Path
from app.core.exceptions import QuotaExceeded
from app.core.deps import get_current_username
from app.core.config import settings
from app.infrastructure.jobs_store import JobsStore
from app.models.schemas import (
    CreateJobRequest,
    CreateJobResponse,
    CancelJobResponse,
    JobResponse,
    PreviewRequest,
    PreviewResponse,
    VideoQualityPreviewResponse,
)
from app.services.media_preview import MediaPreviewer

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


@router.post("/preview", response_model=PreviewResponse)
async def preview_job(
    payload: PreviewRequest,
    username: str = Depends(get_current_username),
) -> PreviewResponse:
    _ = username
    try:
        preview = await asyncio.to_thread(MediaPreviewer().preview, payload.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PreviewResponse(
        url=preview.url,
        webpage_url=preview.webpage_url,
        title=preview.title,
        thumbnail=preview.thumbnail,
        uploader=preview.uploader,
        duration_seconds=preview.duration_seconds,
        is_playlist=preview.is_playlist,
        playlist_count=preview.playlist_count,
        audio_ext=preview.audio_ext,
        audio_filesize_bytes=preview.audio_filesize_bytes,
        video_qualities=[
            VideoQualityPreviewResponse(
                quality=q.quality,
                height=q.height,
                ext=q.ext,
                filesize_bytes=q.filesize_bytes,
                fps=q.fps,
                vcodec=q.vcodec,
                acodec=q.acodec,
            )
            for q in preview.video_qualities
        ],
    )


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
        error_code=job.error_code,
        output_filename=job.output_filename,
        output_type=job.output_type,
        progress_percent=job.progress_percent,
        stage=job.stage,
        updated_at=job.updated_at,
        eta_seconds=job.eta_seconds,
        speed_bps=job.speed_bps,
        playlist_total=job.playlist_total,
        playlist_succeeded=job.playlist_succeeded,
        playlist_failed=job.playlist_failed,
    )


@router.post("/{job_id}/cancel", response_model=CancelJobResponse)
async def cancel_job(
    job_id: str, username: str = Depends(get_current_username)
) -> CancelJobResponse:
    from app.main import get_manager  # noqa

    store = JobsStore()
    job = store.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user != username:
        raise HTTPException(status_code=403, detail="Forbidden")

    manager = get_manager()
    now = _utc_now()

    if job.status == "queued":
        manager.request_cancel(job_id)
        store.update_progress(
            job_id,
            None,
            "canceled",
            updated_at=now,
            eta_seconds=None,
            speed_bps=None,
        )
        store.update_status(
            job_id,
            "canceled",
            finished_at=now,
            error_message="Job canceled by user",
            error_code="CANCELED",
        )
        return CancelJobResponse(job_id=job_id, status="canceled", cancel_requested=True)

    if job.status == "running":
        manager.request_cancel(job_id)
        store.update_progress(
            job_id,
            None,
            "cancel requested",
            updated_at=now,
            eta_seconds=None,
            speed_bps=None,
        )
        return CancelJobResponse(job_id=job_id, status="running", cancel_requested=True)

    if job.status == "canceled":
        return CancelJobResponse(
            job_id=job_id, status="canceled", cancel_requested=False
        )

    raise HTTPException(status_code=409, detail=f"Cannot cancel job in status={job.status}")


def _delete_output_dir(out_dir: Path) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)


@router.get("/{job_id}/download")
def download(
    job_id: str,
    background_tasks: BackgroundTasks,
    username: str = Depends(get_current_username),
):
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
            background_tasks.add_task(_delete_output_dir, out_dir)
            return FileResponse(path=str(p), filename=p.name)

    # 2. Check for common result names (if DB record is empty)
    candidates = ["result.mp3", "result.mp4", "result.mkv", "result.webm", "result.zip"]
    for name in candidates:
        p = out_dir / name
        if p.exists():
            background_tasks.add_task(_delete_output_dir, out_dir)
            return FileResponse(path=str(p), filename=p.name)

    # 3. Last resort: Return the first relevant file in directory
    valid_extensions = {".mp3", ".mp4", ".mkv", ".webm", ".zip"}
    for p in out_dir.iterdir():
        if p.is_file() and p.suffix.lower() in valid_extensions:
            background_tasks.add_task(_delete_output_dir, out_dir)
            return FileResponse(path=str(p), filename=p.name)

    raise HTTPException(status_code=500, detail="No downloadable output found")


@router.get("", response_model=list[JobResponse])
def list_jobs(
    username: str = Depends(get_current_username), limit: int = 50
) -> list[JobResponse]:
    store = JobsStore()
    jobs = store.list_jobs_for_user(user=username, limit=limit)
    return [
        JobResponse(
            job_id=j.job_id,
            user=j.user,
            url=j.url,
            mode=j.mode,
            quality=j.quality,
            status=j.status,
            created_at=j.created_at,
            started_at=j.started_at,
            finished_at=j.finished_at,
            error_message=j.error_message,
            output_filename=j.output_filename,
            output_type=j.output_type,
            error_code=j.error_code,
            progress_percent=j.progress_percent,
            stage=j.stage,
            updated_at=j.updated_at,
            eta_seconds=j.eta_seconds,
            speed_bps=j.speed_bps,
            playlist_total=j.playlist_total,
            playlist_succeeded=j.playlist_succeeded,
            playlist_failed=j.playlist_failed,
        )
        for j in jobs
    ]


@router.get("/{job_id}/events")
async def job_events(job_id: str, username: str = Depends(get_current_username)):
    store = JobsStore()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user != username:
        raise HTTPException(status_code=403, detail="Forbidden")

    async def event_stream():
        last = None
        while True:
            j = store.get_job(job_id)
            if not j:
                break

            payload = {
                "job_id": j.job_id,
                "status": j.status,
                "progress_percent": j.progress_percent,
                "stage": j.stage,
                "updated_at": j.updated_at,
                "error_code": j.error_code,
                "error_message": j.error_message,
                "output_filename": j.output_filename,
                "output_type": j.output_type,
                "eta_seconds": j.eta_seconds,
                "speed_bps": j.speed_bps,
            }

            s = json.dumps(payload, ensure_ascii=False)
            if s != last:
                last = s
                yield f"data: {s}\n\n"

            # stop streaming once finished
            if j.status in ("succeeded", "failed", "canceled"):
                break

            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{job_id}/report")
def download_report(job_id: str, username: str = Depends(get_current_username)):
    store = JobsStore()
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.user != username:
        raise HTTPException(status_code=403, detail="Forbidden")

    out_dir = Path(settings.outputs_dir) / job_id
    report_path = out_dir / "report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found")

    return FileResponse(path=str(report_path), filename="report.json")
