import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.routes_admin_users import (
    create_admin_user,
    disable_admin_user,
    list_admin_users,
    patch_admin_user,
    reset_admin_user_password,
    revoke_admin_user_tokens,
    soft_delete_admin_user,
)
from app.api.routes_auth import login
from app.api.routes_jobs import list_jobs
from app.core.config import settings
from app.core.deps import get_current_user, require_admin
from app.core.security import create_access_token, hash_password
from app.core.users import USER_ROLE_ADMIN, USER_ROLE_USER, USER_STATUS_DISABLED
from app.infrastructure.db import ensure_db_initialized, get_conn
from app.infrastructure.jobs_store import JobsStore
from app.infrastructure.users_repository import UsersRepository
from app.models.schemas import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AdminUpdateUserRequest,
    LoginRequest,
)


class AdminUsersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.old_db_path = settings.db_path
        settings.db_path = str(self.tmp_path / "app.sqlite")
        ensure_db_initialized()
        self.repo = UsersRepository()

    def tearDown(self):
        settings.db_path = self.old_db_path
        self.tmp.cleanup()

    def _create_admin(self, username="admin"):
        return self.repo.create_user(
            username=username,
            password_hash=hash_password("AdminPass123!"),
            role=USER_ROLE_ADMIN,
        )

    def _create_user(self, username="koko", password="UserPass123!"):
        return self.repo.create_user(
            username=username,
            password_hash=hash_password(password),
            role=USER_ROLE_USER,
        )

    def _token_for(self, user):
        return create_access_token(
            subject=user.id,
            extra_claims={
                "username": user.username,
                "role": user.role,
                "token_version": user.token_version,
            },
        )

    def _credentials(self, token: str) -> HTTPAuthorizationCredentials:
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def test_unauthenticated_and_non_admin_requests_are_rejected(self):
        normal = self._create_user()

        with self.assertRaises(HTTPException) as unauth:
            get_current_user(None)
        self.assertEqual(unauth.exception.status_code, 401)

        with self.assertRaises(HTTPException) as forbidden:
            require_admin(current_user=normal)
        self.assertEqual(forbidden.exception.status_code, 403)

    def test_admin_can_create_user_and_password_hash_is_not_returned(self):
        admin = self._create_admin()

        response = create_admin_user(
            AdminCreateUserRequest(
                username="newuser",
                password="NewUser123!",
                email="newuser@example.com",
            ),
            admin_user=admin,
        )

        self.assertEqual(response.username, "newuser")
        self.assertEqual(response.role, USER_ROLE_USER)
        self.assertFalse(hasattr(response, "password_hash"))

        token = login(
            LoginRequest(username="newuser", password="NewUser123!")
        ).access_token
        self.assertTrue(token)

        users = list_admin_users(admin_user=admin, limit=100, offset=0)
        self.assertFalse(any(hasattr(user, "password_hash") for user in users))

    def test_admin_can_disable_user_and_increment_token_version(self):
        admin = self._create_admin()
        user = self._create_user()
        old_version = user.token_version

        response = disable_admin_user(user.id, admin_user=admin)

        self.assertEqual(response.status, USER_STATUS_DISABLED)
        self.assertEqual(response.token_version, old_version + 1)

        with self.assertRaises(HTTPException) as ctx:
            login(LoginRequest(username=user.username, password="UserPass123!"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_revoke_tokens_invalidates_old_access_token(self):
        admin = self._create_admin()
        user = self._create_user()
        old_token = self._token_for(user)

        response = revoke_admin_user_tokens(user.id, admin_user=admin)

        self.assertEqual(response.token_version, user.token_version + 1)
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(self._credentials(old_token))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_admin_can_reset_password(self):
        admin = self._create_admin()
        user = self._create_user()

        reset_admin_user_password(
            user.id,
            AdminResetPasswordRequest(new_password="BetterPass123!"),
            admin_user=admin,
        )

        with self.assertRaises(HTTPException):
            login(LoginRequest(username=user.username, password="UserPass123!"))

        token = login(
            LoginRequest(username=user.username, password="BetterPass123!")
        ).access_token
        self.assertTrue(token)

    def test_soft_deleted_user_cannot_login_and_row_remains(self):
        admin = self._create_admin()
        user = self._create_user()

        response = soft_delete_admin_user(user.id, admin_user=admin)
        stored = self.repo.get_user_by_id(user.id)

        self.assertEqual(response.status, "deleted")
        self.assertIsNotNone(response.deleted_at)
        self.assertIsNotNone(stored)

        with self.assertRaises(HTTPException) as ctx:
            login(LoginRequest(username=user.username, password="UserPass123!"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_admin_cannot_disable_or_soft_delete_themselves(self):
        admin = self._create_admin()

        with self.assertRaises(HTTPException) as disable_ctx:
            disable_admin_user(admin.id, admin_user=admin)
        self.assertEqual(disable_ctx.exception.status_code, 409)

        with self.assertRaises(HTTPException) as delete_ctx:
            soft_delete_admin_user(admin.id, admin_user=admin)
        self.assertEqual(delete_ctx.exception.status_code, 409)

    def test_only_active_admin_cannot_remove_own_admin_role(self):
        admin = self._create_admin()

        with self.assertRaises(HTTPException) as ctx:
            patch_admin_user(
                admin.id,
                AdminUpdateUserRequest(role=USER_ROLE_USER),
                admin_user=admin,
            )

        self.assertEqual(ctx.exception.status_code, 409)

    def test_existing_jobs_endpoint_still_works_for_normal_user(self):
        user = self._create_user()
        current_user = get_current_user(self._credentials(self._token_for(user)))

        JobsStore().create_job(
            job_id="job-1",
            user=current_user.username,
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            mode="audio",
            quality="best",
            status="queued",
            created_at="2026-01-01T00:00:00+00:00",
        )

        jobs = list_jobs(current_user=current_user)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].user, user.username)

    def test_admin_actions_write_audit_logs_without_password_material(self):
        admin = self._create_admin()
        user = create_admin_user(
            AdminCreateUserRequest(username="audited", password="Secret123!"),
            admin_user=admin,
        )
        reset_admin_user_password(
            user.id,
            AdminResetPasswordRequest(new_password="NewSecret123!"),
            admin_user=admin,
        )

        with get_conn() as conn:
            rows = conn.execute("SELECT action, metadata_json FROM audit_logs").fetchall()

        actions = {row["action"] for row in rows}
        metadata = "\n".join(row["metadata_json"] or "" for row in rows)
        self.assertIn("USER_CREATED", actions)
        self.assertIn("USER_PASSWORD_RESET", actions)
        self.assertNotIn("Secret123", metadata)


if __name__ == "__main__":
    unittest.main()
