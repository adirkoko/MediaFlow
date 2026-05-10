from __future__ import annotations

from typing import Any

from app.core.errors import bad_request, conflict, not_found
from app.core.security import hash_password
from app.core.users import (
    ALLOWED_USER_ROLES,
    ALLOWED_USER_STATUSES,
    USER_ROLE_ADMIN,
    USER_ROLE_USER,
    USER_STATUS_ACTIVE,
    USER_STATUS_DELETED,
    USER_STATUS_DISABLED,
    USER_STATUS_LOCKED,
)
from app.infrastructure.audit_logs_repository import AuditLogsRepository
from app.infrastructure.users_repository import UserRecord, UsersRepository


class AdminUsersService:
    def __init__(
        self,
        users: UsersRepository | None = None,
        audit_logs: AuditLogsRepository | None = None,
    ) -> None:
        self._users = users or UsersRepository()
        self._audit_logs = audit_logs or AuditLogsRepository()

    def list_users(
        self,
        status: str | None = None,
        role: str | None = None,
        search: str | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[UserRecord]:
        self._validate_optional_role(role)
        self._validate_optional_status(status)
        return self._users.list_users(
            status=status,
            role=role,
            search=search,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )

    def get_user(self, user_id: str) -> UserRecord:
        return self._get_user_or_404(user_id)

    def create_user(
        self,
        actor: UserRecord,
        username: str,
        password: str,
        email: str | None = None,
        role: str = USER_ROLE_USER,
        status: str = USER_STATUS_ACTIVE,
    ) -> UserRecord:
        clean_username = username.strip()
        clean_email = self._clean_email(email)
        clean_role = self._validate_role(role)
        clean_status = self._validate_status(status)

        if clean_status == USER_STATUS_DELETED:
            raise bad_request("Create users with active, disabled, or locked status")
        if not password:
            raise bad_request("password is required")

        self._ensure_username_available(clean_username)
        self._ensure_email_available(clean_email)

        user = self._users.create_user(
            username=clean_username,
            password_hash=hash_password(password),
            email=clean_email,
            role=clean_role,
            status=clean_status,
        )
        self._audit(
            actor,
            "USER_CREATED",
            user.id,
            {
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "status": user.status,
            },
        )
        return user

    def update_user(
        self,
        actor: UserRecord,
        user_id: str,
        fields: dict[str, Any],
    ) -> UserRecord:
        user = self._get_user_or_404(user_id)
        updates: dict[str, Any] = {}

        if "username" in fields:
            clean_username = str(fields["username"] or "").strip()
            if not clean_username:
                raise bad_request("username is required")
            self._ensure_username_available(clean_username, exclude_user_id=user.id)
            updates["username"] = clean_username

        if "email" in fields:
            clean_email = self._clean_email(fields["email"])
            self._ensure_email_available(clean_email, exclude_user_id=user.id)
            updates["email"] = clean_email

        role_changed = False
        if "role" in fields:
            clean_role = self._validate_role(str(fields["role"]))
            if clean_role != user.role:
                self._ensure_role_change_is_safe(actor, user, clean_role)
                role_changed = True
            updates["role"] = clean_role

        status_changed = False
        if "status" in fields:
            clean_status = self._validate_status(str(fields["status"]))
            if clean_status != user.status:
                self._ensure_status_change_is_safe(actor, user, clean_status)
                status_changed = True
            updates["status"] = clean_status

        if not updates:
            return user

        if updates.get("status") == USER_STATUS_DELETED:
            updated_user = self.soft_delete_user(actor, user.id)
            if len(updates) == 1:
                return updated_user
            updates.pop("status")
            user = updated_user
            status_changed = False

        updated = self._users.update_user(
            user.id,
            updates,
            increment_token_version=role_changed or status_changed,
        )
        if updated is None:
            raise not_found("User not found")

        self._audit(actor, "USER_UPDATED", updated.id, {"fields": sorted(updates)})
        if role_changed:
            self._audit(
                actor,
                "USER_ROLE_CHANGED",
                updated.id,
                {"old_role": user.role, "new_role": updated.role},
            )
        return updated

    def disable_user(self, actor: UserRecord, user_id: str) -> UserRecord:
        user = self._get_user_or_404(user_id)
        self._ensure_not_self(actor, user, "Admins cannot disable themselves")
        self._ensure_not_soft_deleted(user)
        self._users.set_user_status(
            user.id,
            USER_STATUS_DISABLED,
            increment_token_version=True,
        )
        updated = self._get_user_or_404(user.id)
        self._audit(actor, "USER_DISABLED", updated.id, {})
        return updated

    def enable_user(self, actor: UserRecord, user_id: str) -> UserRecord:
        user = self._get_user_or_404(user_id)
        self._ensure_not_soft_deleted(user)
        self._users.set_user_status(
            user.id,
            USER_STATUS_ACTIVE,
            increment_token_version=True,
        )
        updated = self._get_user_or_404(user.id)
        self._audit(actor, "USER_ENABLED", updated.id, {})
        return updated

    def soft_delete_user(self, actor: UserRecord, user_id: str) -> UserRecord:
        user = self._get_user_or_404(user_id)
        self._ensure_not_self(actor, user, "Admins cannot soft-delete themselves")
        self._users.soft_delete_user(user.id)
        updated = self._get_user_or_404(user.id)
        self._audit(actor, "USER_SOFT_DELETED", updated.id, {})
        return updated

    def reset_user_password(
        self,
        actor: UserRecord,
        user_id: str,
        new_password: str,
    ) -> UserRecord:
        user = self._get_user_or_404(user_id)
        if not new_password:
            raise bad_request("new_password is required")
        self._users.reset_user_password(user.id, hash_password(new_password))
        updated = self._get_user_or_404(user.id)
        self._audit(actor, "USER_PASSWORD_RESET", updated.id, {})
        return updated

    def revoke_user_tokens(self, actor: UserRecord, user_id: str) -> UserRecord:
        user = self._get_user_or_404(user_id)
        self._users.increment_user_token_version(user.id)
        updated = self._get_user_or_404(user.id)
        self._audit(actor, "USER_TOKENS_REVOKED", updated.id, {})
        return updated

    def _get_user_or_404(self, user_id: str) -> UserRecord:
        user = self._users.get_user_by_id(user_id)
        if user is None:
            raise not_found("User not found")
        return user

    def _ensure_username_available(
        self,
        username: str,
        exclude_user_id: str | None = None,
    ) -> None:
        existing = self._users.get_user_by_username(username)
        if existing and existing.id != exclude_user_id:
            raise conflict("Username already exists")

    def _ensure_email_available(
        self,
        email: str | None,
        exclude_user_id: str | None = None,
    ) -> None:
        if not email:
            return
        existing = self._users.get_user_by_email(email)
        if existing and existing.id != exclude_user_id:
            raise conflict("Email already exists")

    def _ensure_not_self(
        self,
        actor: UserRecord,
        target: UserRecord,
        message: str,
    ) -> None:
        if actor.id == target.id:
            raise conflict(message)

    def _ensure_not_soft_deleted(self, user: UserRecord) -> None:
        if user.status == USER_STATUS_DELETED or user.deleted_at is not None:
            raise conflict("Soft-deleted users cannot be re-enabled or disabled")

    def _ensure_role_change_is_safe(
        self,
        actor: UserRecord,
        target: UserRecord,
        new_role: str,
    ) -> None:
        if actor.id != target.id:
            return
        if target.role == USER_ROLE_ADMIN and new_role != USER_ROLE_ADMIN:
            if self._users.count_active_admins() <= 1:
                raise conflict("Cannot remove the only active admin role from yourself")

    def _ensure_status_change_is_safe(
        self,
        actor: UserRecord,
        target: UserRecord,
        new_status: str,
    ) -> None:
        if actor.id == target.id and new_status != USER_STATUS_ACTIVE:
            raise conflict("Admins cannot make their own account inactive")
        if target.deleted_at is not None and new_status != USER_STATUS_DELETED:
            raise conflict("Soft-deleted users cannot be re-enabled by update")
        if new_status in {USER_STATUS_DISABLED, USER_STATUS_LOCKED}:
            self._ensure_not_soft_deleted(target)

    def _validate_role(self, role: str) -> str:
        clean_role = role.strip().lower()
        if clean_role not in ALLOWED_USER_ROLES:
            raise bad_request("Unsupported user role")
        return clean_role

    def _validate_status(self, status: str) -> str:
        clean_status = status.strip().lower()
        if clean_status not in ALLOWED_USER_STATUSES:
            raise bad_request("Unsupported user status")
        return clean_status

    def _validate_optional_role(self, role: str | None) -> None:
        if role:
            self._validate_role(role)

    def _validate_optional_status(self, status: str | None) -> None:
        if status:
            self._validate_status(status)

    def _clean_email(self, email: object) -> str | None:
        if isinstance(email, str) and email.strip():
            return email.strip()
        return None

    def _audit(
        self,
        actor: UserRecord,
        action: str,
        target_id: str,
        metadata: dict[str, Any],
    ) -> None:
        self._audit_logs.add_event(
            actor_user_id=actor.id,
            action=action,
            target_type="user",
            target_id=target_id,
            metadata=metadata,
        )
