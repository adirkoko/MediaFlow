import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes_admin_registration_requests import (
    approve_registration_request,
    reject_registration_request,
)
from app.api.routes_auth import login, register_request
from app.core.config import settings
from app.core.deps import require_admin
from app.core.security import hash_password, verify_password
from app.core.users import USER_ROLE_ADMIN, USER_ROLE_USER
from app.infrastructure.db import ensure_db_initialized, get_conn
from app.infrastructure.users_repository import UsersRepository
from app.models.schemas import (
    AdminRejectRegistrationRequest,
    LoginRequest,
    RegistrationRequestCreate,
)


class RegistrationRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.old_db_path = settings.db_path
        self.old_enabled = settings.registration_requests_enabled
        self.old_hour_limit = settings.registration_rate_limit_per_ip_per_hour
        self.old_day_limit = settings.registration_rate_limit_per_ip_per_day
        self.old_pending_limit = settings.registration_max_pending_per_ip
        settings.db_path = str(self.tmp_path / "app.sqlite")
        settings.registration_requests_enabled = True
        settings.registration_rate_limit_per_ip_per_hour = 100
        settings.registration_rate_limit_per_ip_per_day = 100
        settings.registration_max_pending_per_ip = 100
        ensure_db_initialized()
        self.users = UsersRepository()
        self.admin = self.users.create_user(
            username="Admin",
            password_hash=hash_password("AdminPass123!"),
            role=USER_ROLE_ADMIN,
        )
        self.user = self.users.create_user(
            username="normal",
            password_hash=hash_password("UserPass123!"),
            role=USER_ROLE_USER,
        )

    def tearDown(self):
        settings.db_path = self.old_db_path
        settings.registration_requests_enabled = self.old_enabled
        settings.registration_rate_limit_per_ip_per_hour = self.old_hour_limit
        settings.registration_rate_limit_per_ip_per_day = self.old_day_limit
        settings.registration_max_pending_per_ip = self.old_pending_limit
        self.tmp.cleanup()

    def _submit(self, username="KoKo", email="KOKO@Example.com"):
        return register_request(
            RegistrationRequestCreate(
                username=username,
                password="abcd",
                email=email,
                message="  please approve  ",
            )
        )

    def test_public_request_is_stored_pending_with_normalized_identity(self):
        response = self._submit()

        self.assertEqual(response.status, "pending")
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM registration_requests").fetchone()

        self.assertEqual(row["username_normalized"], "koko")
        self.assertEqual(row["email_normalized"], "koko@example.com")
        self.assertEqual(row["message"], "please approve")
        self.assertEqual(row["status"], "pending")
        self.assertNotEqual(row["password_hash"], "abcd")
        self.assertTrue(verify_password("abcd", row["password_hash"]))

    def test_validation_rejects_bad_username_and_short_password(self):
        with self.assertRaises(ValidationError):
            RegistrationRequestCreate(username="קוקו", password="abcd")
        with self.assertRaises(ValidationError):
            RegistrationRequestCreate(username="a", password="abcd")
        with self.assertRaises(ValidationError):
            RegistrationRequestCreate(username="valid", password="abc")

    def test_duplicate_username_is_case_insensitive(self):
        self._submit(username="KoKo", email=None)

        with self.assertRaises(HTTPException) as ctx:
            self._submit(username="koko", email=None)

        self.assertEqual(ctx.exception.status_code, 409)

    def test_existing_user_blocks_registration_request_case_insensitively(self):
        self.users.create_user(username="Taken", password_hash=hash_password("abcd"))

        with self.assertRaises(HTTPException) as ctx:
            self._submit(username="taken", email=None)

        self.assertEqual(ctx.exception.status_code, 409)

    def test_rejected_request_allows_new_pending_request(self):
        self._submit(username="retry", email=None)
        reject_registration_request(
            1,
            AdminRejectRegistrationRequest(reason="not now"),
            admin_user=self.admin,
        )

        self._submit(username="Retry", email=None)

        with get_conn() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM registration_requests WHERE status = 'pending'"
            ).fetchone()["c"]
        self.assertEqual(pending, 1)

    def test_admin_can_approve_and_created_user_can_login(self):
        self._submit(username="NewUser", email="new@example.com")

        created = approve_registration_request(1, admin_user=self.admin)
        token = login(LoginRequest(username="newuser", password="abcd")).access_token

        self.assertEqual(created.username, "newuser")
        self.assertEqual(created.role, USER_ROLE_USER)
        self.assertEqual(created.status, "active")
        self.assertTrue(token)

    def test_admin_can_reject_without_creating_user(self):
        self._submit(username="rejectme", email=None)

        rejected = reject_registration_request(
            1,
            AdminRejectRegistrationRequest(reason="closed group"),
            admin_user=self.admin,
        )

        self.assertEqual(rejected.status, "rejected")
        self.assertIsNone(self.users.get_user_by_username("rejectme"))

    def test_non_admin_is_rejected_by_admin_dependency(self):
        with self.assertRaises(HTTPException) as ctx:
            require_admin(self.user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_rate_limit_blocks_obvious_spam(self):
        settings.registration_rate_limit_per_ip_per_hour = 1
        self._submit(username="first", email=None)

        with self.assertRaises(HTTPException) as ctx:
            self._submit(username="second", email=None)

        self.assertEqual(ctx.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
