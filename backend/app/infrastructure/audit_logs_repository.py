from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.infrastructure.db import get_conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditLogsRepository:
    def add_event(
        self,
        actor_user_id: str,
        action: str,
        target_type: str,
        target_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata_json = json.dumps(metadata or {}, sort_keys=True)
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (
                    actor_user_id, action, target_type, target_id,
                    metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(actor_user_id),
                    action,
                    target_type,
                    str(target_id),
                    metadata_json,
                    _utc_now(),
                ),
            )
            conn.commit()

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, actor_user_id, action, target_type, target_id,
                       metadata_json, created_at
                FROM audit_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 500)),),
            ).fetchall()
            return [dict(row) for row in rows]
