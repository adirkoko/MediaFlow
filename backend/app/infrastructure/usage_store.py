from __future__ import annotations

from typing import Any, Dict

from app.infrastructure.db import get_conn


class UsageStore:
    def add_event(
        self,
        user: str,
        mode: str,
        is_playlist: bool,
        duration_ms: int | None,
        success: bool,
        created_at: str,
    ) -> None:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO usage_events (user, mode, is_playlist, duration_ms, success, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user,
                    mode,
                    1 if is_playlist else 0,
                    duration_ms,
                    1 if success else 0,
                    created_at,
                ),
            )
            conn.commit()

    def get_summary(self, user: str) -> Dict[str, Any]:
        with get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM usage_events WHERE user = ?",
                (user,),
            ).fetchone()["c"]

            success = conn.execute(
                "SELECT COUNT(*) AS c FROM usage_events WHERE user = ? AND success = 1",
                (user,),
            ).fetchone()["c"]

            failed = conn.execute(
                "SELECT COUNT(*) AS c FROM usage_events WHERE user = ? AND success = 0",
                (user,),
            ).fetchone()["c"]

            by_mode_rows = conn.execute(
                """
                SELECT mode, COUNT(*) AS c
                FROM usage_events
                WHERE user = ?
                GROUP BY mode
                """,
                (user,),
            ).fetchall()
            by_mode = {r["mode"]: r["c"] for r in by_mode_rows}

            by_playlist_rows = conn.execute(
                """
                SELECT is_playlist, COUNT(*) AS c
                FROM usage_events
                WHERE user = ?
                GROUP BY is_playlist
                """,
                (user,),
            ).fetchall()
            by_playlist = {
                ("playlist" if r["is_playlist"] == 1 else "single"): r["c"]
                for r in by_playlist_rows
            }

            avg_duration = conn.execute(
                """
                SELECT AVG(duration_ms) AS avg_ms
                FROM usage_events
                WHERE user = ? AND duration_ms IS NOT NULL
                """,
                (user,),
            ).fetchone()["avg_ms"]

        return {
            "total_requests": total,
            "success": success,
            "failed": failed,
            "by_mode": by_mode,
            "by_content_type": by_playlist,
            "avg_duration_ms": int(avg_duration) if avg_duration is not None else None,
        }
