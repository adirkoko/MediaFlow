from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.infrastructure.users_repository import UserRecord
from app.services.quota_service import QuotaService
from app.services.usage_service import UsageService

router = APIRouter(prefix="/me", tags=["usage"])


@router.get("/usage")
def my_usage(
    current_user: UserRecord = Depends(get_current_user),
    range: str = "month",
):
    usage = UsageService().get_user_usage_summary(current_user.id, range)
    return {
        "total_requests": usage["jobs_requested"],
        "success": usage["jobs_succeeded"],
        "failed": usage["jobs_failed"],
        "canceled": usage["jobs_canceled"],
        "by_mode": {
            "audio": usage["audio_jobs"],
            "video": usage["video_jobs"],
        },
        "by_content_type": {
            "single": max(0, usage["jobs_requested"] - usage["playlist_jobs"]),
            "playlist": usage["playlist_jobs"],
        },
        "avg_duration_ms": usage["avg_processing_ms"],
        "credits_estimated": usage["credits_estimated"],
        "credits_used": usage["credits_used"],
        "output_size_bytes": usage["total_output_bytes"],
    }


@router.get("/usage/daily")
def my_daily_usage(
    current_user: UserRecord = Depends(get_current_user),
    days: int = 30,
):
    return UsageService().get_user_daily_usage(current_user.id, days)


@router.get("/limits")
def my_limits(current_user: UserRecord = Depends(get_current_user)):
    return QuotaService().usage_for_limits(current_user)
