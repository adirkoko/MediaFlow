from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.infrastructure.db import get_conn


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SecurityRepository:
    def record_login_attempt(
        self,
        username: str | None,
        user_id: str | None,
        ip_hash: str | None,
        user_agent: str | None,
        success: bool,
        failure_reason: str | None = None,
    ) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO login_attempts (
                    id, username, user_id, ip_hash, user_agent,
                    success, failure_reason, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    username,
                    user_id,
                    ip_hash,
                    user_agent,
                    int(success),
                    failure_reason,
                    _utc_now().isoformat(),
                ),
            )
            conn.commit()

    def count_failed_attempts(
        self,
        since_minutes: int,
        username: str | None = None,
        ip_hash: str | None = None,
    ) -> int:
        cutoff = (_utc_now() - timedelta(minutes=max(1, since_minutes))).isoformat()
        clauses = ["success = 0", "created_at >= ?"]
        args: list[Any] = [cutoff]
        if username:
            clauses.append("lower(username) = ?")
            args.append(username.lower())
        if ip_hash:
            clauses.append("ip_hash = ?")
            args.append(ip_hash)

        with get_conn() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM login_attempts WHERE {' AND '.join(clauses)}",
                tuple(args),
            ).fetchone()
            return int(row["c"])

    def list_login_attempts(self, limit: int = 100) -> list[dict[str, Any]]:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, username, user_id, ip_hash, user_agent,
                       success, failure_reason, created_at
                FROM login_attempts
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def blocked_logins(self, window_minutes: int, threshold: int) -> list[dict[str, Any]]:
        cutoff = (_utc_now() - timedelta(minutes=max(1, window_minutes))).isoformat()
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT username, ip_hash, COUNT(*) AS failed_attempts, MAX(created_at) AS last_attempt_at
                FROM login_attempts
                WHERE success = 0 AND created_at >= ?
                GROUP BY username, ip_hash
                HAVING COUNT(*) >= ?
                ORDER BY failed_attempts DESC, last_attempt_at DESC
                """,
                (cutoff, max(1, int(threshold))),
            ).fetchall()
            return [dict(row) for row in rows]
