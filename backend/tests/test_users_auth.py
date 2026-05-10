import json
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.routes_auth import login
from app.api.routes_jobs import list_jobs
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, decode_access_token, hash_password
from app.core.users import USER_ROLE_USER, USER_STATUS_DISABLED
from app.infrastructure.db import ensure_db_initialized, get_conn
from app.infrastructure.jobs_store import JobsStore
from app.infrastructure.users_repository import UsersRepository
from app.models.schemas import LoginRequest
from scripts.migrate_users_json_to_db import migrate_users_json_to_db


class UsersAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.old_db_path = settings.db_path
        self.old_users_file = settings.users_file
        settings.db_path = str(self.tmp_path / "app.sqlite")
        settings.users_file = str(self.tmp_path / "users.json")
        ensure_db_initialized()

    def tearDown(self):
        settings.db_path = self.old_db_path
        settings.users_file = self.old_users_file
        self.tmp.cleanup()

    def _repo(self) -> UsersRepository:
        return UsersRepository()

    def _credentials(self, token: str) -> HTTPAuthorizationCredentials:
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def test_db_user_can_login_and_receives_new_jwt_payload(self):
        repo = self._repo()
        user = repo.create_user(
            username="koko",
            password_hash=hash_password("Correct123!"),
        )

        token = login(
            LoginRequest(username="koko", password="Correct123!")
        ).access_token
        payload = decode_access_token(token)
        fresh_user = repo.get_user_by_id(user.id)

        self.assertEqual(payload["sub"], user.id)
        self.assertEqual(payload["username"], "koko")
        self.assertEqual(payload["role"], USER_ROLE_USER)
        self.assertEqual(payload["token_version"], 1)
        self.assertIsNotNone(fresh_user)
        self.assertIsNotNone(fresh_user.last_login_at)

    def test_wrong_password_fails(self):
        self._repo().create_user(
            username="koko",
            password_hash=hash_password("Correct123!"),
        )

        with self.assertRaises(HTTPException) as ctx:
            login(LoginRequest(username="koko", password="wrong"))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_disabled_user_cannot_login(self):
        repo = self._repo()
        user = repo.create_user(
            username="koko",
            password_hash=hash_password("Correct123!"),
        )
        repo.set_user_status(user.id, USER_STATUS_DISABLED)

        with self.assertRaises(HTTPException) as ctx:
            login(LoginRequest(username="koko", password="Correct123!"))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_soft_deleted_user_cannot_login(self):
        repo = self._repo()
        user = repo.create_user(
            username="koko",
            password_hash=hash_password("Correct123!"),
        )
        repo.soft_delete_user(user.id)

        with self.assertRaises(HTTPException) as ctx:
            login(LoginRequest(username="koko", password="Correct123!"))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_valid_token_resolves_current_user_and_can_list_own_jobs(self):
        repo = self._repo()
        user = repo.create_user(
            username="koko",
            password_hash=hash_password("Correct123!"),
        )
        token = create_access_token(
            subject=user.id,
            extra_claims={
                "username": user.username,
                "role": user.role,
                "token_version": user.token_version,
            },
        )
        current_user = get_current_user(self._credentials(token))

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
        self.assertEqual(jobs[0].user, "koko")

    def test_old_token_version_is_rejected(self):
        repo = self._repo()
        user = repo.create_user(
            username="koko",
            password_hash=hash_password("Correct123!"),
        )
        token = create_access_token(
            subject=user.id,
            extra_claims={
                "username": user.username,
                "role": user.role,
                "token_version": user.token_version,
            },
        )
        repo.increment_user_token_version(user.id)

        with self.assertRaises(HTTPException) as ctx:
            get_current_user(self._credentials(token))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_legacy_username_subject_token_is_rejected_cleanly(self):
        self._repo().create_user(
            username="koko",
            password_hash=hash_password("Correct123!"),
        )
        legacy_token = create_access_token(subject="koko")

        with self.assertRaises(HTTPException) as ctx:
            get_current_user(self._credentials(legacy_token))

        self.assertEqual(ctx.exception.status_code, 401)

    def test_users_json_migration_is_idempotent(self):
        users_file = self.tmp_path / "users.json"
        users_file.write_text(
            json.dumps(
                {
                    "users": [
                        {
                            "username": "koko",
                            "password_hash": hash_password("Correct123!"),
                        },
                        {
                            "username": "kokos",
                            "password_hash": hash_password("Correct123!"),
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        first = migrate_users_json_to_db(users_file=users_file)
        second = migrate_users_json_to_db(users_file=users_file)

        with get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]

        self.assertEqual(first.inserted, 2)
        self.assertEqual(second.inserted, 0)
        self.assertEqual(second.skipped_existing, 2)
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
