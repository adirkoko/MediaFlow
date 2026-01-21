from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.infrastructure.db import get_conn

log = logging.getLogger("cleanup")


def _parse_iso(dt: str) -> datetime:
    # stored as datetime.now(timezone.utc).isoformat()
    return datetime.fromisoformat(dt)


@dataclass(frozen=True)
class CleanupStats:
    deleted_dirs: int = 0
    errors: int = 0


class OutputsCleaner:
    async def run_forever(self) -> None:
        interval = max(1, settings.outputs_cleanup_interval_minutes) * 60
        log.info(
            "OutputsCleaner started (ttl_hours=%s, interval_min=%s)",
            settings.outputs_ttl_hours,
            settings.outputs_cleanup_interval_minutes,
        )
        while True:
            try:
                stats = await asyncio.to_thread(self.cleanup_once)
                if stats.deleted_dirs or stats.errors:
                    log.info(
                        "Cleanup run finished: deleted=%s errors=%s",
                        stats.deleted_dirs,
                        stats.errors,
                    )
            except Exception:
                log.exception("Cleanup run failed")
            await asyncio.sleep(interval)

    def cleanup_once(self) -> CleanupStats:
        ttl = timedelta(hours=max(1, settings.outputs_ttl_hours))
        cutoff = datetime.now(timezone.utc) - ttl

        outputs_root = Path(settings.outputs_dir)
        if not outputs_root.exists():
            return CleanupStats()

        # Select jobs finished before cutoff (succeeded/failed only)
        with get_conn() as conn:
            rows = conn.execute(
                """
                SELECT job_id
                FROM jobs
                WHERE finished_at IS NOT NULL
                  AND status IN ('succeeded', 'failed')
                """
            ).fetchall()

        deleted = 0
        errors = 0

        for row in rows:
            job_id = row["job_id"]
            # Fetch finished_at to compare
            with get_conn() as conn:
                r = conn.execute(
                    "SELECT finished_at FROM jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
            if not r or not r["finished_at"]:
                continue

            try:
                finished_at = _parse_iso(r["finished_at"])
            except Exception:
                # bad data; skip
                continue

            if finished_at > cutoff:
                continue

            job_dir = outputs_root / job_id
            if not job_dir.exists():
                continue

            try:
                shutil.rmtree(job_dir, ignore_errors=False)
                deleted += 1
            except Exception:
                errors += 1
                log.exception("Failed deleting outputs dir for job_id=%s", job_id)

        return CleanupStats(deleted_dirs=deleted, errors=errors)
