import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.api.routes_admin_quotas import (
    delete_user_quota,
    get_user_quota,
    patch_role_quota,
    patch_user_quota,
)
from app.api.routes_auth import login
from app.api.routes_jobs import create_job
from app.api.routes_usage import my_limits, my_usage
from app.core.config import settings
from app.core.security import hash_password
from app.core.users import USER_ROLE_ADMIN, USER_ROLE_USER
from app.infrastructure.db import ensure_db_initialized, get_conn
from app.infrastructure.jobs_store import JobsStore
from app.infrastructure.quotas_repository import QuotasRepository
from app.infrastructure.users_repository import UsersRepository
from app.models.schemas import CreateJobRequest, LoginRequest, MediaMode, QuotaUpdateRequest
from app.services.quota_service import QuotaService
from app.services.rate_limiter import rate_limiter
from app.services.usage_service import UsageService


class Phase3QuotasUsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.old_db_path = settings.db_path
        self.old_create_limit = settings.job_create_rate_limit_per_minute
        self.old_preview_limit = settings.job_preview_rate_limit_per_minute
        self.old_login_limit = settings.login_max_failed_per_username
        settings.db_path = str(self.tmp_path / "app.sqlite")
        settings.job_create_rate_limit_per_minute = 100
        settings.job_preview_rate_limit_per_minute = 100
        settings.login_max_failed_per_username = 5
        rate_limiter.clear()
        ensure_db_initialized()
        self.users = UsersRepository()
        self.admin = self.users.create_user(
            username="admin",
            password_hash=hash_password("AdminPass123!"),
            role=USER_ROLE_ADMIN,
        )
        self.user = self.users.create_user(
            username="koko",
            password_hash=hash_password("UserPass123!"),
            role=USER_ROLE_USER,
        )

    def tearDown(self):
        settings.db_path = self.old_db_path
        settings.job_create_rate_limit_per_minute = self.old_create_limit
        settings.job_preview_rate_limit_per_minute = self.old_preview_limit
        settings.login_max_failed_per_username = self.old_login_limit
        rate_limiter.clear()
        self.tmp.cleanup()

    def test_default_role_quota_and_user_override_precedence(self):
        effective = QuotaService().get_effective_quota(self.user)
        self.assertEqual(effective.max_video_quality, "1080p")

        patch_user_quota(
            self.user.id,
            QuotaUpdateRequest(max_video_quality="720p", max_jobs_per_day=3),
            admin_user=self.admin,
        )
        overridden = get_user_quota(self.user.id, admin_user=self.admin)
        self.assertEqual(overridden.effective_quota["max_video_quality"], "720p")
        self.assertEqual(overridden.effective_quota["max_jobs_per_day"], 3)

        delete_user_quota(self.user.id, admin_user=self.admin)
        fallback = get_user_quota(self.user.id, admin_user=self.admin)
        self.assertEqual(fallback.effective_quota["max_video_quality"], "1080p")

    def test_exceeding_daily_jobs_returns_429(self):
        patch_role_quota(
            "user",
            QuotaUpdateRequest(max_jobs_per_day=1),
            admin_user=self.admin,
        )
        UsageService().record_job_requested(
            user_id=self.user.id,
            job_id="existing",
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mode="audio",
            quality="best",
            estimated_credits=1,
            is_playlist=False,
            playlist_items=1,
        )

        with self.assertRaises(HTTPException) as ctx:
            QuotaService().check_can_create_job(
                self.user,
                url="https://www.youtube.com/watch?v=abc",
                mode="audio",
                quality="best",
            )

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.detail["error"], "DAY_JOBS_QUOTA_EXCEEDED")

    def test_exceeding_daily_credits_and_quality_are_rejected(self):
        patch_role_quota(
            "user",
            QuotaUpdateRequest(max_credits_per_day=1, max_video_quality="720p"),
            admin_user=self.admin,
        )

        with self.assertRaises(HTTPException) as quality_ctx:
            QuotaService().check_can_create_job(
                self.user,
                url="https://www.youtube.com/watch?v=abc",
                mode="video",
                quality="1080p",
            )
        self.assertEqual(quality_ctx.exception.status_code, 429)

        with self.assertRaises(HTTPException) as credit_ctx:
            QuotaService().check_can_create_job(
                self.user,
                url="https://www.youtube.com/watch?v=abc",
                mode="video",
                quality="720p",
            )
        self.assertEqual(credit_ctx.exception.detail["error"], "DAY_CREDITS_QUOTA_EXCEEDED")

    def test_active_jobs_limit_and_allowed_job_creation(self):
        patch_role_quota(
            "user",
            QuotaUpdateRequest(max_active_jobs=1, max_video_quality="2160p"),
            admin_user=self.admin,
        )
        JobsStore().create_job(
            job_id="active",
            user=self.user.username,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mode="audio",
            quality="best",
            status="queued",
            created_at="2026-01-01T00:00:00+00:00",
        )
        with self.assertRaises(HTTPException):
            QuotaService().check_can_create_job(
                self.user,
                url="https://www.youtube.com/watch?v=abc",
                mode="audio",
                quality="best",
            )

    def test_job_requested_updates_usage_and_me_limits(self):
        estimate = QuotaService().check_can_create_job(
            self.user,
            url="https://www.youtube.com/watch?v=abc",
            mode="audio",
            quality="best",
        )
        QuotaService().reserve_usage_for_job(
            self.user,
            job_id="job-1",
            url="https://www.youtube.com/watch?v=abc",
            mode="audio",
            quality="best",
            estimate=estimate,
        )

        usage = my_usage(current_user=self.user, range="today")
        limits = my_limits(current_user=self.user)

        self.assertEqual(usage["total_requests"], 1)
        self.assertEqual(usage["credits_estimated"], 1)
        self.assertGreaterEqual(limits["remaining"]["today"]["jobs"], 0)

    def test_create_job_route_records_requested_usage(self):
        response = asyncio.run(
            create_job(
                CreateJobRequest(
                    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    mode=MediaMode.audio,
                    quality="best",
                ),
                current_user=self.user,
            )
        )
        self.assertEqual(response.status, "queued")
        usage = UsageService().get_user_usage_summary(self.user.id, "today")
        self.assertEqual(usage["jobs_requested"], 1)

    def test_job_lifecycle_usage_events_update_daily_aggregate(self):
        usage_service = UsageService()
        usage_service.record_job_started(self.user.id, "job-1", "audio", "best")
        usage_service.record_job_finished(
            user_id=self.user.id,
            job_id="job-1",
            event_type="job_succeeded",
            mode="audio",
            quality="best",
            actual_credits=1,
            processing_time_ms=1200,
            output_size_bytes=2048,
        )

        summary = usage_service.get_user_usage_summary(self.user.id, "today")

        self.assertEqual(summary["jobs_started"], 1)
        self.assertEqual(summary["jobs_succeeded"], 1)
        self.assertEqual(summary["credits_used"], 1)
        self.assertEqual(summary["total_output_bytes"], 2048)

    def test_login_failed_attempts_are_recorded_and_blocked(self):
        settings.login_max_failed_per_username = 2
        for _ in range(2):
            with self.assertRaises(HTTPException):
                login(LoginRequest(username="koko", password="wrong"))

        with self.assertRaises(HTTPException) as ctx:
            login(LoginRequest(username="koko", password="wrong"))

        self.assertEqual(ctx.exception.status_code, 429)
        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM login_attempts").fetchone()["c"]
        self.assertGreaterEqual(count, 3)

    def test_job_create_rate_limit_returns_429(self):
        settings.job_create_rate_limit_per_minute = 1
        asyncio.run(
            create_job(
                CreateJobRequest(
                    url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    mode=MediaMode.audio,
                    quality="best",
                ),
                current_user=self.user,
            )
        )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                create_job(
                    CreateJobRequest(
                        url="https://www.youtube.com/watch?v=abc",
                        mode=MediaMode.audio,
                        quality="best",
                    ),
                    current_user=self.user,
                )
            )

        self.assertEqual(ctx.exception.status_code, 429)

    def test_admin_usage_and_quota_exceeded_events_exist(self):
        with self.assertRaises(HTTPException):
            QuotaService().check_quality_allowed(
                QuotaService().get_effective_quota(self.user),
                requested_quality="2160p",
                mode="video",
            )

        with get_conn() as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertIn("role_quotas", tables)
        self.assertIn("user_quotas", tables)
        self.assertIn("usage_events", tables)
        self.assertIn("user_usage_daily", tables)
        self.assertIn("login_attempts", tables)


if __name__ == "__main__":
    unittest.main()
