from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.core.users import (
    ALLOWED_USER_ROLES,
    ALLOWED_USER_STATUSES,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    USER_STATUS_DELETED,
)
from app.infrastructure.db import get_conn


@dataclass(frozen=True)
class UserRecord:
    id: str
    username: str
    email: Optional[str]
    password_hash: str
    role: str
    status: str
    token_version: int
    created_at: str
    updated_at: str
    last_login_at: Optional[str]
    deleted_at: Optional[str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_user(row) -> UserRecord | None:
    if not row:
        return None
    return UserRecord(**dict(row))


def _validate_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ALLOWED_USER_ROLES:
        raise ValueError(f"Unsupported user role: {role}")
    return normalized


def _validate_status(status: str) -> str:
    normalized = status.strip().lower()
    if normalized not in ALLOWED_USER_STATUSES:
        raise ValueError(f"Unsupported user status: {status}")
    return normalized


class UsersRepository:
    def get_user_by_id(self, user_id: str) -> UserRecord | None:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (str(user_id),)).fetchone()
            return _row_to_user(row)

    def get_user_by_username(self, username: str) -> UserRecord | None:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
            return _row_to_user(row)

    def create_user(
        self,
        username: str,
        password_hash: str,
        email: str | None = None,
        role: str = USER_ROLE_USER,
    ) -> UserRecord:
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("username is required")
        if not password_hash:
            raise ValueError("password_hash is required")

        clean_email = email.strip() if isinstance(email, str) and email.strip() else None
        clean_role = _validate_role(role)
        now = _utc_now()
        user_id = uuid.uuid4().hex

        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, username, email, password_hash, role, status,
                    token_version, created_at, updated_at, last_login_at, deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    user_id,
                    clean_username,
                    clean_email,
                    password_hash,
                    clean_role,
                    USER_STATUS_ACTIVE,
                    1,
                    now,
                    now,
                ),
            )
            conn.commit()

        user = self.get_user_by_id(user_id)
        if user is None:
            raise RuntimeError("User was created but could not be loaded")
        return user

    def update_user_last_login(self, user_id: str) -> None:
        now = _utc_now()
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE users
                SET last_login_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, str(user_id)),
            )
            conn.commit()

    def increment_user_token_version(self, user_id: str) -> None:
        now = _utc_now()
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE users
                SET token_version = token_version + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, str(user_id)),
            )
            conn.commit()

    def set_user_status(self, user_id: str, status: str) -> None:
        clean_status = _validate_status(status)
        now = _utc_now()
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE users
                SET status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (clean_status, now, str(user_id)),
            )
            conn.commit()

    def soft_delete_user(self, user_id: str) -> None:
        now = _utc_now()
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE users
                SET status = ?,
                    deleted_at = COALESCE(deleted_at, ?),
                    token_version = token_version + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (USER_STATUS_DELETED, now, now, str(user_id)),
            )
            conn.commit()
