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
from app.core.registration import normalize_email, normalize_username
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
        clean_username = normalize_username(username)
        if not clean_username:
            return None
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE lower(username) = ?",
                (clean_username,),
            ).fetchone()
            return _row_to_user(row)

    def get_user_by_email(self, email: str) -> UserRecord | None:
        clean_email = normalize_email(email)
        if not clean_email:
            return None

        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE lower(email) = ?",
                (clean_email,),
            ).fetchone()
            return _row_to_user(row)

    def list_users(
        self,
        status: str | None = None,
        role: str | None = None,
        search: str | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UserRecord]:
        clauses: list[str] = []
        args: list[object] = []

        if status:
            clauses.append("status = ?")
            args.append(_validate_status(status))
        elif not include_deleted:
            clauses.append("status != ?")
            args.append(USER_STATUS_DELETED)

        if not include_deleted:
            clauses.append("deleted_at IS NULL")

        if role:
            clauses.append("role = ?")
            args.append(_validate_role(role))

        if search and search.strip():
            pattern = f"%{search.strip().lower()}%"
            clauses.append("(lower(username) LIKE ? OR lower(COALESCE(email, '')) LIKE ?)")
            args.extend([pattern, pattern])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        args.extend([safe_limit, safe_offset])

        with get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM users
                {where}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(args),
            ).fetchall()
            return [UserRecord(**dict(row)) for row in rows]

    def create_user(
        self,
        username: str,
        password_hash: str,
        email: str | None = None,
        role: str = USER_ROLE_USER,
        status: str = USER_STATUS_ACTIVE,
    ) -> UserRecord:
        clean_username = normalize_username(username)
        if not clean_username:
            raise ValueError("username is required")
        if not password_hash:
            raise ValueError("password_hash is required")

        clean_email = normalize_email(email)
        clean_role = _validate_role(role)
        clean_status = _validate_status(status)
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
                    clean_status,
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

    def update_user(
        self,
        user_id: str,
        fields: dict[str, object],
        increment_token_version: bool = False,
    ) -> UserRecord | None:
        allowed = {"username", "email", "role", "status"}
        updates: list[str] = []
        args: list[object] = []

        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f"Unsupported user field: {key}")
            if key == "username":
                clean_username = normalize_username(str(value or ""))
                if not clean_username:
                    raise ValueError("username is required")
                updates.append("username = ?")
                args.append(clean_username)
            elif key == "email":
                clean_email = normalize_email(str(value) if value is not None else None)
                updates.append("email = ?")
                args.append(clean_email)
            elif key == "role":
                updates.append("role = ?")
                args.append(_validate_role(str(value)))
            elif key == "status":
                clean_status = _validate_status(str(value))
                updates.append("status = ?")
                args.append(clean_status)
                if clean_status == USER_STATUS_DELETED:
                    updates.append("deleted_at = COALESCE(deleted_at, ?)")
                    args.append(_utc_now())

        if not updates:
            return self.get_user_by_id(user_id)

        updates.append("updated_at = ?")
        args.append(_utc_now())

        if increment_token_version:
            updates.append("token_version = token_version + 1")

        args.append(str(user_id))

        with get_conn() as conn:
            conn.execute(
                f"""
                UPDATE users
                SET {', '.join(updates)}
                WHERE id = ?
                """,
                tuple(args),
            )
            conn.commit()

        return self.get_user_by_id(user_id)

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

    def set_user_status(
        self,
        user_id: str,
        status: str,
        increment_token_version: bool = False,
    ) -> None:
        clean_status = _validate_status(status)
        now = _utc_now()
        updates = ["status = ?", "updated_at = ?"]
        args: list[object] = [clean_status, now]
        if increment_token_version:
            updates.append("token_version = token_version + 1")
        args.append(str(user_id))

        with get_conn() as conn:
            conn.execute(
                f"""
                UPDATE users
                SET {', '.join(updates)}
                WHERE id = ?
                """,
                tuple(args),
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

    def reset_user_password(self, user_id: str, password_hash: str) -> None:
        if not password_hash:
            raise ValueError("password_hash is required")

        now = _utc_now()
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE users
                SET password_hash = ?,
                    token_version = token_version + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (password_hash, now, str(user_id)),
            )
            conn.commit()

    def count_active_admins(self) -> int:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM users
                WHERE role = 'admin'
                  AND status = 'active'
                  AND deleted_at IS NULL
                """
            ).fetchone()
            return int(row["c"])
