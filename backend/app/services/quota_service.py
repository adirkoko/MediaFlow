from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException

from app.infrastructure.jobs_store import JobsStore
from app.infrastructure.audit_logs_repository import AuditLogsRepository
from app.infrastructure.quotas_repository import QUOTA_FIELDS, QuotaRecord, QuotasRepository
from app.infrastructure.users_repository import UserRecord
from app.services.download_validation import SUPPORTED_VIDEO_QUALITY_HEIGHTS, normalize_quality
from app.services.usage_service import UsageService


QUALITY_ORDER = {
    "144p": 144,
    "240p": 240,
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p": 2160,
    "best": 2160,
}

VIDEO_CREDITS = {
    "best": 5,
    "144p": 1,
    "240p": 1,
    "360p": 2,
    "480p": 2,
    "720p": 3,
    "1080p": 5,
    "1440p": 8,
    "2160p": 12,
}


@dataclass(frozen=True)
class EffectiveQuota:
    values: dict[str, Any]

    def __getattr__(self, name: str) -> Any:
        if name in self.values:
            return self.values[name]
        raise AttributeError(name)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.values)


@dataclass(frozen=True)
class JobCostEstimate:
    estimated_credits: int
    playlist_items: int
    is_playlist: bool
    duration_seconds: int | None


def _reset_at(days: int) -> str:
    now = datetime.now(timezone.utc)
    if days == 1:
        target = (now + timedelta(days=1)).date()
    elif days == 7:
        target = (now + timedelta(days=7)).date()
    else:
        target = (now + timedelta(days=30)).date()
    return datetime.combine(target, datetime.min.time(), tzinfo=timezone.utc).isoformat()


class QuotaExceeded(HTTPException):
    def __init__(
        self,
        error: str,
        message: str,
        limit: int | None = None,
        used: int | None = None,
        requested: int | None = None,
        reset_at: str | None = None,
    ) -> None:
        super().__init__(
            status_code=429,
            detail={
                "error": error,
                "message": message,
                "limit": limit,
                "used": used,
                "requested": requested,
                "reset_at": reset_at,
            },
        )


class QuotaService:
    def __init__(
        self,
        quotas: QuotasRepository | None = None,
        usage: UsageService | None = None,
        jobs: JobsStore | None = None,
    ) -> None:
        self._quotas = quotas or QuotasRepository()
        self._usage = usage or UsageService()
        self._jobs = jobs or JobsStore()
        self._audit = AuditLogsRepository()

    def get_effective_quota(self, user: UserRecord) -> EffectiveQuota:
        role_quota = self._quotas.get_role_quota(user.role).quota.to_dict()
        user_quota = self._quotas.get_user_quota(user.id)
        if user_quota:
            for field, value in user_quota.quota.to_dict().items():
                if value is not None:
                    role_quota[field] = value
        return EffectiveQuota(role_quota)

    def estimate_job_cost(
        self,
        mode: str,
        quality: str,
        url: str,
        preview_data: Any | None = None,
    ) -> JobCostEstimate:
        clean_mode = mode.strip().lower()
        clean_quality = normalize_quality(quality)
        is_playlist = self._is_playlist(url, preview_data)
        playlist_items = self._playlist_items(url, preview_data, is_playlist)
        duration_seconds = getattr(preview_data, "duration_seconds", None) if preview_data else None

        if clean_mode == "audio":
            per_item = 1
        else:
            per_item = VIDEO_CREDITS.get(clean_quality, VIDEO_CREDITS["best"])

        multiplier = 1
        if isinstance(duration_seconds, int) and duration_seconds > 3600:
            multiplier += duration_seconds // 3600

        return JobCostEstimate(
            estimated_credits=max(1, per_item * max(1, playlist_items) * multiplier),
            playlist_items=max(1, playlist_items),
            is_playlist=is_playlist,
            duration_seconds=duration_seconds,
        )

    def check_can_create_job(
        self,
        user: UserRecord,
        url: str,
        mode: str,
        quality: str,
        preview_data: Any | None = None,
    ) -> JobCostEstimate:
        quota = self.get_effective_quota(user)
        estimate = self.estimate_job_cost(mode, quality, url, preview_data)
        try:
            self.check_active_jobs_limit(user, quota)
            self.check_quality_allowed(quota, quality, mode)
            self.check_playlist_limit(user, quota, estimate)
            self.check_duration_limit(quota, estimate)
            self.check_periodic_limits(user, quota, estimate.estimated_credits, estimate.playlist_items)
        except QuotaExceeded as exc:
            self._usage.record_quota_exceeded(
                user_id=user.id,
                url=url,
                mode=mode,
                quality=quality,
                reason=exc.detail["error"],
                metadata=exc.detail,
            )
            self._audit.add_event(
                actor_user_id="system",
                action="QUOTA_EXCEEDED",
                target_type="user",
                target_id=user.id,
                metadata=exc.detail,
            )
            raise
        return estimate

    def check_active_jobs_limit(self, user: UserRecord, quota: EffectiveQuota) -> None:
        limit = quota.max_active_jobs
        if limit is None:
            return
        active = self._jobs.count_active_jobs_for_user(user.username)
        if active >= int(limit):
            raise QuotaExceeded(
                "ACTIVE_JOBS_LIMIT_EXCEEDED",
                "Too many active jobs",
                limit=int(limit),
                used=active,
                requested=1,
            )

    def check_quality_allowed(self, quota: EffectiveQuota, requested_quality: str, mode: str) -> None:
        if mode == "audio":
            return
        requested = normalize_quality(requested_quality)
        max_quality = normalize_quality(str(quota.max_video_quality or "2160p"))
        if requested not in QUALITY_ORDER or max_quality not in QUALITY_ORDER:
            return
        if QUALITY_ORDER[requested] > QUALITY_ORDER[max_quality]:
            raise QuotaExceeded(
                "VIDEO_QUALITY_LIMIT_EXCEEDED",
                "Requested video quality exceeds your limit",
                limit=QUALITY_ORDER[max_quality],
                used=0,
                requested=QUALITY_ORDER[requested],
            )

    def check_playlist_limit(
        self,
        user: UserRecord,
        quota: EffectiveQuota,
        estimate: JobCostEstimate,
    ) -> None:
        if not estimate.is_playlist:
            return
        per_job = quota.max_playlist_items_per_job
        if per_job is not None and estimate.playlist_items > int(per_job):
            raise QuotaExceeded(
                "PLAYLIST_ITEMS_PER_JOB_EXCEEDED",
                "Playlist item limit exceeded",
                limit=int(per_job),
                used=0,
                requested=estimate.playlist_items,
            )
        per_day = quota.max_playlist_items_per_day
        if per_day is not None:
            usage = self._usage.get_user_usage_summary(user.id, "today")
            used = int(usage.get("playlist_items_requested", 0))
            if used + estimate.playlist_items > int(per_day):
                raise QuotaExceeded(
                    "PLAYLIST_ITEMS_PER_DAY_EXCEEDED",
                    "Daily playlist item limit exceeded",
                    limit=int(per_day),
                    used=used,
                    requested=estimate.playlist_items,
                    reset_at=_reset_at(1),
                )

    def check_duration_limit(self, quota: EffectiveQuota, estimate: JobCostEstimate) -> None:
        limit = quota.max_video_duration_seconds
        if limit is None or estimate.duration_seconds is None:
            return
        if estimate.duration_seconds > int(limit):
            raise QuotaExceeded(
                "VIDEO_DURATION_LIMIT_EXCEEDED",
                "Video duration exceeds your limit",
                limit=int(limit),
                used=0,
                requested=estimate.duration_seconds,
            )

    def check_periodic_limits(
        self,
        user: UserRecord,
        quota: EffectiveQuota,
        estimated_credits: int,
        playlist_items: int,
    ) -> None:
        windows = [
            ("day", "today", 1, quota.max_jobs_per_day, quota.max_credits_per_day),
            ("week", "week", 7, quota.max_jobs_per_week, quota.max_credits_per_week),
            ("month", "month", 30, quota.max_jobs_per_month, quota.max_credits_per_month),
        ]
        for label, range_name, days, jobs_limit, credits_limit in windows:
            usage = self._usage.get_user_usage_summary(user.id, range_name)
            jobs_used = int(usage.get("jobs_requested", 0))
            credits_used = int(usage.get("credits_estimated", 0))
            if jobs_limit is not None and jobs_used + 1 > int(jobs_limit):
                raise QuotaExceeded(
                    f"{label.upper()}_JOBS_QUOTA_EXCEEDED",
                    f"{label.capitalize()} job quota exceeded",
                    limit=int(jobs_limit),
                    used=jobs_used,
                    requested=1,
                    reset_at=_reset_at(days),
                )
            if credits_limit is not None and credits_used + estimated_credits > int(credits_limit):
                raise QuotaExceeded(
                    f"{label.upper()}_CREDITS_QUOTA_EXCEEDED",
                    f"{label.capitalize()} credit quota exceeded",
                    limit=int(credits_limit),
                    used=credits_used,
                    requested=estimated_credits,
                    reset_at=_reset_at(days),
                )

    def reserve_usage_for_job(
        self,
        user: UserRecord,
        job_id: str,
        url: str,
        mode: str,
        quality: str,
        estimate: JobCostEstimate,
    ) -> None:
        self._usage.record_job_requested(
            user_id=user.id,
            job_id=job_id,
            url=url,
            mode=mode,
            quality=quality,
            estimated_credits=estimate.estimated_credits,
            is_playlist=estimate.is_playlist,
            playlist_items=estimate.playlist_items,
            duration_seconds=estimate.duration_seconds,
            metadata={"source": "quota_reservation"},
        )

    def usage_for_limits(self, user: UserRecord) -> dict[str, Any]:
        quota = self.get_effective_quota(user)
        today = self._usage.get_user_usage_summary(user.id, "today")
        week = self._usage.get_user_usage_summary(user.id, "week")
        month = self._usage.get_user_usage_summary(user.id, "month")
        return {
            "effective_quota": quota.to_dict(),
            "usage": {"today": today, "week": week, "month": month},
            "remaining": {
                "today": self._remaining(quota, today, "day"),
                "week": self._remaining(quota, week, "week"),
                "month": self._remaining(quota, month, "month"),
            },
            "max_active_jobs": quota.max_active_jobs,
            "max_video_quality": quota.max_video_quality,
            "playlist_limits": {
                "max_playlist_items_per_job": quota.max_playlist_items_per_job,
                "max_playlist_items_per_day": quota.max_playlist_items_per_day,
            },
            "max_video_duration_seconds": quota.max_video_duration_seconds,
        }

    def _remaining(self, quota: EffectiveQuota, usage: dict[str, Any], window: str) -> dict[str, Any]:
        jobs_limit = getattr(quota, f"max_jobs_per_{window}")
        credits_limit = getattr(quota, f"max_credits_per_{window}")
        return {
            "jobs": None if jobs_limit is None else max(0, int(jobs_limit) - int(usage.get("jobs_requested", 0))),
            "credits": None if credits_limit is None else max(0, int(credits_limit) - int(usage.get("credits_estimated", 0))),
        }

    def _is_playlist(self, url: str, preview_data: Any | None) -> bool:
        if preview_data is not None:
            return bool(getattr(preview_data, "is_playlist", False))
        parsed = urlparse(url)
        return bool(parse_qs(parsed.query).get("list"))

    def _playlist_items(self, url: str, preview_data: Any | None, is_playlist: bool) -> int:
        if preview_data is not None:
            count = getattr(preview_data, "playlist_count", None)
            if isinstance(count, int) and count > 0:
                return count
        return 10 if is_playlist else 1


def validate_quota_updates(updates: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for field, value in updates.items():
        if field not in QUOTA_FIELDS:
            continue
        if value is None:
            clean[field] = None
            continue
        if field == "max_video_quality":
            q = normalize_quality(str(value))
            if q not in SUPPORTED_VIDEO_QUALITY_HEIGHTS:
                raise HTTPException(status_code=400, detail="Unsupported video quality")
            clean[field] = q
            continue
        int_value = int(value)
        if int_value <= 0:
            raise HTTPException(status_code=400, detail=f"{field} must be positive")
        clean[field] = int_value
    return clean
