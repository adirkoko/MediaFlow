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
    progress_percent: Optional[int]
    stage: Optional[str]
    updated_at: Optional[str]
    eta_seconds: Optional[int]
    speed_bps: Optional[int]
    playlist_total: Optional[int]
    playlist_succeeded: Optional[int]
    playlist_failed: Optional[int]




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
        playlist_total: Optional[int] = None,
        playlist_succeeded: Optional[int] = None,
        playlist_failed: Optional[int] = None,

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
                    output_type = COALESCE(?, output_type),
                    error_code = COALESCE(?, error_code),
                    request_fingerprint = COALESCE(?, request_fingerprint),
                    playlist_total = COALESCE(?, playlist_total),
                    playlist_succeeded = COALESCE(?, playlist_succeeded),
                    playlist_failed = COALESCE(?, playlist_failed)
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
                    playlist_total,
                    playlist_succeeded,
                    playlist_failed,
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

    def list_active_jobs(self, limit: int = 1000) -> list[JobRecord]:
        limit = max(1, min(int(limit), 20000))
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM jobs
                WHERE status IN ('queued', 'running')
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [JobRecord(**dict(r)) for r in rows]

    def list_jobs_for_user(self, user: str, limit: int = 50) -> list[JobRecord]:
        limit = max(1, min(int(limit), 200))
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM jobs
                WHERE user = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user, limit),
            ).fetchall()
            return [JobRecord(**dict(r)) for r in rows]

    def list_jobs_admin(
        self,
        user: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JobRecord]:
        clauses: list[str] = []
        args: list[object] = []
        if user:
            clauses.append("user = ?")
            args.append(user)
        if status:
            clauses.append("status = ?")
            args.append(status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        args.extend([safe_limit, safe_offset])

        with get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM jobs
                {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(args),
            ).fetchall()
            return [JobRecord(**dict(r)) for r in rows]

    def update_progress(
        self,
        job_id: str,
        progress_percent: int | None,
        stage: str | None,
        updated_at: str,
        eta_seconds: int | None = None,
        speed_bps: int | None = None,
    ) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET progress_percent = COALESCE(?, progress_percent),
                    stage = COALESCE(?, stage),
                    updated_at = ?,
                    eta_seconds = COALESCE(?, eta_seconds),
                    speed_bps = COALESCE(?, speed_bps)
                WHERE job_id = ?
                """,
                (progress_percent, stage, updated_at, eta_seconds, speed_bps, job_id),
            )
            conn.commit()


