from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.infrastructure.db import get_conn


QUOTA_FIELDS = (
    "max_active_jobs",
    "max_jobs_per_day",
    "max_jobs_per_week",
    "max_jobs_per_month",
    "max_credits_per_day",
    "max_credits_per_week",
    "max_credits_per_month",
    "max_playlist_items_per_job",
    "max_playlist_items_per_day",
    "max_video_duration_seconds",
    "max_video_quality",
    "max_output_mb_per_day",
    "max_output_mb_per_month",
)


@dataclass(frozen=True)
class QuotaRecord:
    max_active_jobs: int | None
    max_jobs_per_day: int | None
    max_jobs_per_week: int | None
    max_jobs_per_month: int | None
    max_credits_per_day: int | None
    max_credits_per_week: int | None
    max_credits_per_month: int | None
    max_playlist_items_per_job: int | None
    max_playlist_items_per_day: int | None
    max_video_duration_seconds: int | None
    max_video_quality: str | None
    max_output_mb_per_day: int | None
    max_output_mb_per_month: int | None

    @classmethod
    def from_row(cls, row) -> "QuotaRecord":
        data = dict(row)
        return cls(**{field: data.get(field) for field in QUOTA_FIELDS})

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in QUOTA_FIELDS}


@dataclass(frozen=True)
class RoleQuotaRecord:
    role: str
    quota: QuotaRecord
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class UserQuotaRecord:
    user_id: str
    quota: QuotaRecord
    created_at: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fallback_role_quota(role: str) -> QuotaRecord:
    if role == "admin":
        return QuotaRecord(
            max_active_jobs=10,
            max_jobs_per_day=500,
            max_jobs_per_week=2500,
            max_jobs_per_month=10000,
            max_credits_per_day=2000,
            max_credits_per_week=10000,
            max_credits_per_month=40000,
            max_playlist_items_per_job=200,
            max_playlist_items_per_day=1000,
            max_video_duration_seconds=14400,
            max_video_quality="2160p",
            max_output_mb_per_day=None,
            max_output_mb_per_month=None,
        )
    return QuotaRecord(
        max_active_jobs=settings.max_active_jobs_per_user,
        max_jobs_per_day=50,
        max_jobs_per_week=250,
        max_jobs_per_month=1000,
        max_credits_per_day=200,
        max_credits_per_week=1000,
        max_credits_per_month=4000,
        max_playlist_items_per_job=50,
        max_playlist_items_per_day=200,
        max_video_duration_seconds=7200,
        max_video_quality="1080p",
        max_output_mb_per_day=None,
        max_output_mb_per_month=None,
    )


class QuotasRepository:
    def list_role_quotas(self) -> list[RoleQuotaRecord]:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM role_quotas ORDER BY role").fetchall()
            return [
                RoleQuotaRecord(
                    role=row["role"],
                    quota=QuotaRecord.from_row(row),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def get_role_quota(self, role: str) -> RoleQuotaRecord:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM role_quotas WHERE role = ?",
                (role,),
            ).fetchone()
        if row:
            return RoleQuotaRecord(
                role=row["role"],
                quota=QuotaRecord.from_row(row),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        now = _utc_now()
        return RoleQuotaRecord(role=role, quota=_fallback_role_quota(role), created_at=now, updated_at=now)

    def update_role_quota(self, role: str, updates: dict[str, Any]) -> RoleQuotaRecord:
        now = _utc_now()
        current = self.get_role_quota(role)
        values = current.quota.to_dict()
        values.update({k: v for k, v in updates.items() if k in QUOTA_FIELDS})

        columns = ["role", *QUOTA_FIELDS, "created_at", "updated_at"]
        placeholders = ", ".join("?" for _ in columns)
        update_clause = ", ".join(f"{field} = excluded.{field}" for field in [*QUOTA_FIELDS, "updated_at"])
        args = [role, *(values[field] for field in QUOTA_FIELDS), current.created_at, now]

        with get_conn() as conn:
            conn.execute(
                f"""
                INSERT INTO role_quotas ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(role) DO UPDATE SET {update_clause}
                """,
                tuple(args),
            )
            conn.commit()
        return self.get_role_quota(role)

    def get_user_quota(self, user_id: str) -> UserQuotaRecord | None:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM user_quotas WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return UserQuotaRecord(
            user_id=row["user_id"],
            quota=QuotaRecord.from_row(row),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def upsert_user_quota(self, user_id: str, updates: dict[str, Any]) -> UserQuotaRecord:
        now = _utc_now()
        current = self.get_user_quota(user_id)
        values = {field: None for field in QUOTA_FIELDS}
        created_at = now
        if current:
            values.update(current.quota.to_dict())
            created_at = current.created_at
        values.update({k: v for k, v in updates.items() if k in QUOTA_FIELDS})

        columns = ["user_id", *QUOTA_FIELDS, "created_at", "updated_at"]
        placeholders = ", ".join("?" for _ in columns)
        update_clause = ", ".join(f"{field} = excluded.{field}" for field in [*QUOTA_FIELDS, "updated_at"])
        args = [user_id, *(values[field] for field in QUOTA_FIELDS), created_at, now]

        with get_conn() as conn:
            conn.execute(
                f"""
                INSERT INTO user_quotas ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(user_id) DO UPDATE SET {update_clause}
                """,
                tuple(args),
            )
            conn.commit()
        record = self.get_user_quota(user_id)
        if record is None:
            raise RuntimeError("User quota was not saved")
        return record

    def delete_user_quota(self, user_id: str) -> None:
        with get_conn() as conn:
            conn.execute("DELETE FROM user_quotas WHERE user_id = ?", (user_id,))
            conn.commit()
