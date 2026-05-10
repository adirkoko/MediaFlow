from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.registration import (
    ALLOWED_REGISTRATION_STATUSES,
    REGISTRATION_STATUS_PENDING,
)
from app.infrastructure.db import get_conn


@dataclass(frozen=True)
class RegistrationRequestRecord:
    id: int
    username: str
    username_normalized: str
    password_hash: str
    email: str | None
    email_normalized: str | None
    message: str | None
    status: str
    requested_at: str
    reviewed_at: str | None
    reviewed_by_user_id: str | None
    decision_reason: str | None
    request_ip_hash: str | None
    user_agent: str | None
    created_at: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_request(row: Any) -> RegistrationRequestRecord | None:
    if not row:
        return None
    return RegistrationRequestRecord(**dict(row))


class RegistrationRequestsRepository:
    def create_request(
        self,
        username: str,
        username_normalized: str,
        password_hash: str,
        email: str | None,
        email_normalized: str | None,
        message: str | None,
        request_ip_hash: str | None,
        user_agent: str | None,
    ) -> RegistrationRequestRecord:
        now = _utc_now()
        with get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO registration_requests (
                    username, username_normalized, password_hash, email,
                    email_normalized, message, status, requested_at,
                    request_ip_hash, user_agent, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    username_normalized,
                    password_hash,
                    email,
                    email_normalized,
                    message,
                    now,
                    request_ip_hash,
                    user_agent,
                    now,
                    now,
                ),
            )
            request_id = int(cur.lastrowid)
            conn.commit()

        request = self.get_request(request_id)
        if request is None:
            raise RuntimeError("Registration request was created but could not be loaded")
        return request

    def get_request(self, request_id: int) -> RegistrationRequestRecord | None:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM registration_requests WHERE id = ?",
                (int(request_id),),
            ).fetchone()
            return _row_to_request(row)

    def get_pending_by_username(
        self, username_normalized: str
    ) -> RegistrationRequestRecord | None:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM registration_requests
                WHERE username_normalized = ?
                  AND status = 'pending'
                ORDER BY requested_at DESC
                LIMIT 1
                """,
                (username_normalized,),
            ).fetchone()
            return _row_to_request(row)

    def get_pending_by_email(
        self, email_normalized: str
    ) -> RegistrationRequestRecord | None:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM registration_requests
                WHERE email_normalized = ?
                  AND status = 'pending'
                ORDER BY requested_at DESC
                LIMIT 1
                """,
                (email_normalized,),
            ).fetchone()
            return _row_to_request(row)

    def list_requests(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RegistrationRequestRecord]:
        clauses: list[str] = []
        args: list[object] = []
        if status and status != "all":
            clean_status = status.strip().lower()
            if clean_status not in ALLOWED_REGISTRATION_STATUSES:
                raise ValueError("Unsupported registration request status")
            clauses.append("status = ?")
            args.append(clean_status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        args.extend([safe_limit, safe_offset])

        with get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM registration_requests
                {where}
                ORDER BY
                    CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                    requested_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(args),
            ).fetchall()
            return [RegistrationRequestRecord(**dict(row)) for row in rows]

    def count_recent_by_ip(self, ip_hash: str, hours: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))).isoformat()
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM registration_requests
                WHERE request_ip_hash = ?
                  AND requested_at >= ?
                """,
                (ip_hash, cutoff),
            ).fetchone()
            return int(row["c"])

    def count_pending_by_ip(self, ip_hash: str) -> int:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM registration_requests
                WHERE request_ip_hash = ?
                  AND status = 'pending'
                """,
                (ip_hash,),
            ).fetchone()
            return int(row["c"])

    def mark_approved(self, request_id: int, reviewed_by_user_id: str) -> None:
        self._mark_reviewed(
            request_id=request_id,
            status="approved",
            reviewed_by_user_id=reviewed_by_user_id,
            decision_reason=None,
        )

    def mark_rejected(
        self,
        request_id: int,
        reviewed_by_user_id: str,
        decision_reason: str | None,
    ) -> None:
        self._mark_reviewed(
            request_id=request_id,
            status="rejected",
            reviewed_by_user_id=reviewed_by_user_id,
            decision_reason=decision_reason,
        )

    def _mark_reviewed(
        self,
        request_id: int,
        status: str,
        reviewed_by_user_id: str,
        decision_reason: str | None,
    ) -> None:
        now = _utc_now()
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE registration_requests
                SET status = ?,
                    reviewed_at = ?,
                    reviewed_by_user_id = ?,
                    decision_reason = ?,
                    updated_at = ?
                WHERE id = ?
                  AND status = ?
                """,
                (
                    status,
                    now,
                    reviewed_by_user_id,
                    decision_reason,
                    now,
                    int(request_id),
                    REGISTRATION_STATUS_PENDING,
                ),
            )
            conn.commit()
