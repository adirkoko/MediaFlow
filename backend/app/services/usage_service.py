from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.infrastructure.usage_repository import UsageEventInput, UsageRepository

log = logging.getLogger("usage")


def url_hash(url: str | None) -> str | None:
    if not url:
        return None
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def range_to_days(range_name: str | None) -> int:
    value = (range_name or "today").strip().lower()
    if value == "today":
        return 1
    if value == "week":
        return 7
    if value == "month":
        return 30
    return 1


class UsageService:
    def __init__(self, repo: UsageRepository | None = None) -> None:
        self._repo = repo or UsageRepository()

    def safe_record(self, event: UsageEventInput) -> None:
        try:
            self._repo.record_event(event)
        except Exception:
            log.exception("Failed recording usage event type=%s", event.event_type)

    def record_job_requested(
        self,
        user_id: str,
        job_id: str,
        url: str,
        mode: str,
        quality: str,
        estimated_credits: int,
        is_playlist: bool,
        playlist_items: int,
        duration_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.safe_record(
            UsageEventInput(
                user_id=user_id,
                job_id=job_id,
                event_type="job_requested",
                mode=mode,
                quality=quality,
                is_playlist=is_playlist,
                playlist_items_requested=playlist_items,
                requested_url_hash=url_hash(url),
                estimated_credits=estimated_credits,
                duration_seconds=duration_seconds,
                metadata=metadata,
            )
        )

    def record_job_started(self, user_id: str, job_id: str, mode: str, quality: str) -> None:
        self.safe_record(
            UsageEventInput(
                user_id=user_id,
                job_id=job_id,
                event_type="job_started",
                mode=mode,
                quality=quality,
            )
        )

    def record_job_finished(
        self,
        user_id: str,
        job_id: str,
        event_type: str,
        mode: str,
        quality: str,
        estimated_credits: int | None = None,
        actual_credits: int | None = None,
        processing_time_ms: int | None = None,
        output_size_bytes: int | None = None,
        is_playlist: bool | None = None,
        playlist_items_succeeded: int | None = None,
        playlist_items_failed: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.safe_record(
            UsageEventInput(
                user_id=user_id,
                job_id=job_id,
                event_type=event_type,
                mode=mode,
                quality=quality,
                estimated_credits=estimated_credits,
                actual_credits=actual_credits,
                processing_time_ms=processing_time_ms,
                output_size_bytes=output_size_bytes,
                is_playlist=is_playlist,
                playlist_items_succeeded=playlist_items_succeeded,
                playlist_items_failed=playlist_items_failed,
                error_code=error_code,
            )
        )

    def record_quota_exceeded(
        self,
        user_id: str,
        url: str,
        mode: str,
        quality: str,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        self.safe_record(
            UsageEventInput(
                user_id=user_id,
                event_type="quota_exceeded",
                mode=mode,
                quality=quality,
                requested_url_hash=url_hash(url),
                status="rejected",
                error_code=reason,
                metadata=metadata,
            )
        )

    def record_rate_limited(
        self,
        user_id: str,
        endpoint: str,
        metadata: dict[str, Any],
    ) -> None:
        self.safe_record(
            UsageEventInput(
                user_id=user_id,
                event_type="rate_limited",
                status="rejected",
                error_code="RATE_LIMITED",
                metadata={"endpoint": endpoint, **metadata},
            )
        )

    def record_download_result(
        self,
        user_id: str,
        job_id: str,
        output_size_bytes: int | None,
    ) -> None:
        self.safe_record(
            UsageEventInput(
                user_id=user_id,
                job_id=job_id,
                event_type="download_result",
                output_size_bytes=output_size_bytes,
            )
        )

    def get_user_usage_summary(self, user_id: str, range_name: str = "today") -> dict[str, Any]:
        return self._repo.summarize_user(user_id, range_to_days(range_name))

    def get_user_daily_usage(self, user_id: str, days: int = 30) -> list[dict[str, Any]]:
        return self._repo.get_user_daily_rows(user_id, days)

    def get_admin_usage_summary(self, range_name: str = "today") -> dict[str, Any]:
        return self._repo.summarize_all_users(range_to_days(range_name))

    def get_heavy_users(self, range_name: str = "today", limit: int = 20) -> list[dict[str, Any]]:
        return self._repo.heavy_users(range_to_days(range_name), limit=limit)

    def list_quota_exceeded(self, range_name: str = "today", limit: int = 100) -> list[dict[str, Any]]:
        return self._repo.list_events(
            event_type="quota_exceeded",
            days=range_to_days(range_name),
            limit=limit,
        )
