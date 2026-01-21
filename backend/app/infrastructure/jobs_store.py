from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta, timezone
from app.infrastructure.db import get_conn


@dataclass(frozen=True)
class JobRecord:
    job_id: str
    user: str
    url: str
    mode: str
    quality: str
    status: str
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]
    error_message: Optional[str]
    output_filename: Optional[str]
    output_type: Optional[str]
    error_code: Optional[str]
    request_fingerprint: Optional[str]


class JobsStore:
    def create_job(
        self,
        job_id: str,
        user: str,
        url: str,
        mode: str,
        quality: str,
        status: str,
        created_at: str,
    ) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, user, url, mode, quality, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (job_id, user, url, mode, quality, status, created_at),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not row:
                return None
            return JobRecord(**dict(row))

    def update_status(
        self,
        job_id: str,
        status: str,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        error_message: Optional[str] = None,
        output_filename: Optional[str] = None,
        output_type: Optional[str] = None,
        error_code: Optional[str] = None,
        request_fingerprint: Optional[str] = None,
    ) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    started_at = COALESCE(?, started_at),
                    finished_at = COALESCE(?, finished_at),
                    error_message = COALESCE(?, error_message),
                    output_filename = COALESCE(?, output_filename),
                    output_type = COALESCE(?, output_type)
                    error_code = COALESCE(?, error_code),
                    request_fingerprint = COALESCE(?, request_fingerprint)
                WHERE job_id = ?
                """,
                (
                    status,
                    started_at,
                    finished_at,
                    error_message,
                    output_filename,
                    output_type,
                    error_code,
                    request_fingerprint,
                    job_id,
                ),
            )
            conn.commit()

    def count_active_jobs_for_user(self, user: str) -> int:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM jobs
                WHERE user = ?
                  AND status IN ('queued', 'running')
                """,
                (user,),
            ).fetchone()
            return int(row["c"])

    def find_duplicate_active_job(
        self, user: str, fingerprint: str, window_minutes: int
    ) -> str | None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(1, window_minutes))
        cutoff_iso = cutoff.isoformat()

        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT job_id
                FROM jobs
                WHERE user = ?
                  AND request_fingerprint = ?
                  AND status IN ('queued', 'running')
                  AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user, fingerprint, cutoff_iso),
            ).fetchone()
            return str(row["job_id"]) if row else None
