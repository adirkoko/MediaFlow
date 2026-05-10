from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.infrastructure.db import get_conn


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def utc_date(dt: datetime | None = None) -> str:
    return (dt or utc_now()).date().isoformat()


@dataclass(frozen=True)
class UsageEventInput:
    user_id: str
    event_type: str
    job_id: str | None = None
    mode: str | None = None
    quality: str | None = None
    is_playlist: bool | None = None
    playlist_items_requested: int | None = None
    playlist_items_succeeded: int | None = None
    playlist_items_failed: int | None = None
    requested_url_hash: str | None = None
    estimated_credits: int | None = None
    actual_credits: int | None = None
    processing_time_ms: int | None = None
    duration_seconds: int | None = None
    output_size_bytes: int | None = None
    status: str | None = None
    error_code: str | None = None
    metadata: dict[str, Any] | None = None


class UsageRepository:
    def record_event(self, event: UsageEventInput) -> str:
        event_id = uuid.uuid4().hex
        created_at = utc_now_iso()
        metadata_json = json.dumps(event.metadata or {}, sort_keys=True)
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (
                    id, user_id, job_id, event_type, mode, quality, is_playlist,
                    playlist_items_requested, playlist_items_succeeded,
                    playlist_items_failed, requested_url_hash, estimated_credits,
                    actual_credits, processing_time_ms, duration_seconds,
                    output_size_bytes, status, error_code, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event.user_id,
                    event.job_id,
                    event.event_type,
                    event.mode,
                    event.quality,
                    None if event.is_playlist is None else int(event.is_playlist),
                    event.playlist_items_requested,
                    event.playlist_items_succeeded,
                    event.playlist_items_failed,
                    event.requested_url_hash,
                    event.estimated_credits,
                    event.actual_credits,
                    event.processing_time_ms,
                    event.duration_seconds,
                    event.output_size_bytes,
                    event.status,
                    event.error_code,
                    metadata_json,
                    created_at,
                ),
            )
            self._update_daily(conn, event, created_at)
            conn.commit()
        return event_id

    def _ensure_daily_row(self, conn, user_id: str, date: str, updated_at: str) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO user_usage_daily (user_id, date, updated_at)
            VALUES (?, ?, ?)
            """,
            (user_id, date, updated_at),
        )

    def _update_daily(self, conn, event: UsageEventInput, created_at: str) -> None:
        date = created_at[:10]
        self._ensure_daily_row(conn, event.user_id, date, created_at)

        updates: dict[str, int] = {}
        if event.event_type == "job_requested":
            updates["jobs_requested"] = 1
            updates["credits_estimated"] = event.estimated_credits or 0
            updates["playlist_items_requested"] = event.playlist_items_requested or 0
            if event.mode == "audio":
                updates["audio_jobs"] = 1
            if event.mode == "video":
                updates["video_jobs"] = 1
            if event.is_playlist:
                updates["playlist_jobs"] = 1
        elif event.event_type == "job_started":
            updates["jobs_started"] = 1
        elif event.event_type == "job_succeeded":
            updates["jobs_succeeded"] = 1
            updates["credits_used"] = event.actual_credits or event.estimated_credits or 0
            updates["total_processing_ms"] = event.processing_time_ms or 0
            updates["total_output_bytes"] = event.output_size_bytes or 0
            updates["playlist_items_succeeded"] = event.playlist_items_succeeded or 0
            updates["playlist_items_failed"] = event.playlist_items_failed or 0
        elif event.event_type == "job_failed":
            updates["jobs_failed"] = 1
            updates["total_processing_ms"] = event.processing_time_ms or 0
            updates["playlist_items_failed"] = event.playlist_items_failed or 0
        elif event.event_type == "job_canceled":
            updates["jobs_canceled"] = 1
            updates["total_processing_ms"] = event.processing_time_ms or 0
        elif event.event_type == "download_result":
            updates["total_output_bytes"] = event.output_size_bytes or 0

        if not updates:
            return

        set_clause = ", ".join(f"{field} = {field} + ?" for field in updates)
        args = [*updates.values(), created_at, event.user_id, date]
        conn.execute(
            f"""
            UPDATE user_usage_daily
            SET {set_clause}, updated_at = ?
            WHERE user_id = ? AND date = ?
            """,
            tuple(args),
        )
        conn.execute(
            """
            UPDATE user_usage_daily
            SET avg_processing_ms = CASE
                WHEN (jobs_succeeded + jobs_failed + jobs_canceled) > 0
                THEN total_processing_ms / (jobs_succeeded + jobs_failed + jobs_canceled)
                ELSE 0
            END
            WHERE user_id = ? AND date = ?
            """,
            (event.user_id, date),
        )

    def get_user_daily_rows(self, user_id: str, days: int = 30) -> list[dict[str, Any]]:
        safe_days = max(1, min(int(days), 365))
        start = (utc_now().date() - timedelta(days=safe_days - 1)).isoformat()
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM user_usage_daily
                WHERE user_id = ? AND date >= ?
                ORDER BY date DESC
                """,
                (user_id, start),
            ).fetchall()
            return [dict(row) for row in rows]

    def summarize_user(self, user_id: str, days: int) -> dict[str, Any]:
        start = (utc_now().date() - timedelta(days=max(1, days) - 1)).isoformat()
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(jobs_requested), 0) AS jobs_requested,
                    COALESCE(SUM(jobs_started), 0) AS jobs_started,
                    COALESCE(SUM(jobs_succeeded), 0) AS jobs_succeeded,
                    COALESCE(SUM(jobs_failed), 0) AS jobs_failed,
                    COALESCE(SUM(jobs_canceled), 0) AS jobs_canceled,
                    COALESCE(SUM(audio_jobs), 0) AS audio_jobs,
                    COALESCE(SUM(video_jobs), 0) AS video_jobs,
                    COALESCE(SUM(playlist_jobs), 0) AS playlist_jobs,
                    COALESCE(SUM(credits_estimated), 0) AS credits_estimated,
                    COALESCE(SUM(credits_used), 0) AS credits_used,
                    COALESCE(SUM(total_processing_ms), 0) AS total_processing_ms,
                    COALESCE(SUM(total_output_bytes), 0) AS total_output_bytes,
                    COALESCE(SUM(playlist_items_requested), 0) AS playlist_items_requested,
                    COALESCE(SUM(playlist_items_succeeded), 0) AS playlist_items_succeeded,
                    COALESCE(SUM(playlist_items_failed), 0) AS playlist_items_failed
                FROM user_usage_daily
                WHERE user_id = ? AND date >= ?
                """,
                (user_id, start),
            ).fetchone()
        data = dict(row)
        finished = data["jobs_succeeded"] + data["jobs_failed"] + data["jobs_canceled"]
        data["avg_processing_ms"] = int(data["total_processing_ms"] / finished) if finished else 0
        return data

    def summarize_all_users(self, days: int) -> dict[str, Any]:
        start = (utc_now().date() - timedelta(days=max(1, days) - 1)).isoformat()
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(jobs_requested), 0) AS jobs_requested,
                    COALESCE(SUM(jobs_succeeded), 0) AS jobs_succeeded,
                    COALESCE(SUM(jobs_failed), 0) AS jobs_failed,
                    COALESCE(SUM(jobs_canceled), 0) AS jobs_canceled,
                    COALESCE(SUM(credits_used), 0) AS credits_used,
                    COALESCE(SUM(total_output_bytes), 0) AS total_output_bytes,
                    COALESCE(SUM(total_processing_ms), 0) AS total_processing_ms,
                    COALESCE(SUM(playlist_items_requested), 0) AS playlist_items_requested
                FROM user_usage_daily
                WHERE date >= ?
                """,
                (start,),
            ).fetchone()
        data = dict(row)
        finished = data["jobs_succeeded"] + data["jobs_failed"] + data["jobs_canceled"]
        data["avg_processing_ms"] = int(data["total_processing_ms"] / finished) if finished else 0
        return data

    def heavy_users(self, days: int, limit: int = 20) -> list[dict[str, Any]]:
        start = (utc_now().date() - timedelta(days=max(1, days) - 1)).isoformat()
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT user_id,
                       COALESCE(SUM(jobs_requested), 0) AS jobs_requested,
                       COALESCE(SUM(credits_used), 0) AS credits_used,
                       COALESCE(SUM(credits_estimated), 0) AS credits_estimated,
                       COALESCE(SUM(total_output_bytes), 0) AS total_output_bytes
                FROM user_usage_daily
                WHERE date >= ?
                GROUP BY user_id
                ORDER BY credits_used DESC, credits_estimated DESC, jobs_requested DESC
                LIMIT ?
                """,
                (start, max(1, min(int(limit), 100))),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_events(self, event_type: str | None = None, days: int = 7, limit: int = 100) -> list[dict[str, Any]]:
        start = (utc_now() - timedelta(days=max(1, days))).isoformat()
        args: list[Any] = [start]
        where = "created_at >= ?"
        if event_type:
            where += " AND event_type = ?"
            args.append(event_type)
        args.append(max(1, min(int(limit), 500)))
        with get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM usage_events
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple(args),
            ).fetchall()
            return [dict(row) for row in rows]
