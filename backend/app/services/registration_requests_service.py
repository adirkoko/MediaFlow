from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.errors import bad_request, conflict, not_found
from app.core.registration import (
    REGISTRATION_STATUS_PENDING,
    USERNAME_PATTERN,
    normalize_email,
    normalize_username,
)
from app.core.security import hash_password
from app.core.users import USER_ROLE_USER, USER_STATUS_ACTIVE
from app.infrastructure.audit_logs_repository import AuditLogsRepository
from app.infrastructure.registration_requests_repository import (
    RegistrationRequestRecord,
    RegistrationRequestsRepository,
)
from app.infrastructure.users_repository import UserRecord, UsersRepository
from app.services.login_protection import request_ip_hash, request_user_agent

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UNAVAILABLE_MESSAGE = "This username or email is unavailable."


class RegistrationRequestsService:
    def __init__(
        self,
        requests: RegistrationRequestsRepository | None = None,
        users: UsersRepository | None = None,
        audit_logs: AuditLogsRepository | None = None,
    ) -> None:
        self._requests = requests or RegistrationRequestsRepository()
        self._users = users or UsersRepository()
        self._audit = audit_logs or AuditLogsRepository()

    def submit_request(
        self,
        username: str,
        password: str,
        email: str | None,
        message: str | None,
        request: Request | None = None,
    ) -> RegistrationRequestRecord:
        if not settings.registration_requests_enabled:
            raise HTTPException(status_code=403, detail="Registration requests are disabled")

        clean_username = self._validate_username(username)
        clean_email = self._validate_email(email)
        clean_message = self._validate_message(message)
        self._validate_password(password)

        ip_hash = request_ip_hash(request)
        self._check_rate_limits(ip_hash)
        self._ensure_identity_available(clean_username, clean_email)

        try:
            return self._requests.create_request(
                username=clean_username,
                username_normalized=clean_username,
                password_hash=hash_password(password),
                email=clean_email,
                email_normalized=clean_email,
                message=clean_message,
                request_ip_hash=ip_hash,
                user_agent=request_user_agent(request),
            )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper():
                raise conflict(UNAVAILABLE_MESSAGE)
            raise

    def list_requests(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RegistrationRequestRecord]:
        try:
            return self._requests.list_requests(status=status, limit=limit, offset=offset)
        except ValueError as exc:
            raise bad_request(str(exc))

    def approve_request(self, actor: UserRecord, request_id: int) -> UserRecord:
        request = self._get_pending_request(request_id)
        self._ensure_identity_available(
            request.username_normalized,
            request.email_normalized,
            ignore_request_id=request.id,
        )

        user = self._users.create_user(
            username=request.username_normalized,
            password_hash=request.password_hash,
            email=request.email_normalized,
            role=USER_ROLE_USER,
            status=USER_STATUS_ACTIVE,
        )
        self._requests.mark_approved(request.id, actor.id)
        self._audit.add_event(
            actor_user_id=actor.id,
            action="REGISTRATION_REQUEST_APPROVED",
            target_type="registration_request",
            target_id=str(request.id),
            metadata={
                "created_user_id": user.id,
                "username": user.username,
            },
        )
        return user

    def reject_request(
        self,
        actor: UserRecord,
        request_id: int,
        reason: str | None = None,
    ) -> RegistrationRequestRecord:
        request = self._get_pending_request(request_id)
        clean_reason = self._validate_decision_reason(reason)
        self._requests.mark_rejected(request.id, actor.id, clean_reason)
        updated = self._requests.get_request(request.id)
        if updated is None:
            raise not_found("Registration request not found")
        self._audit.add_event(
            actor_user_id=actor.id,
            action="REGISTRATION_REQUEST_REJECTED",
            target_type="registration_request",
            target_id=str(request.id),
            metadata={
                "username": request.username_normalized,
                "has_reason": bool(clean_reason),
            },
        )
        return updated

    def _get_pending_request(self, request_id: int) -> RegistrationRequestRecord:
        request = self._requests.get_request(request_id)
        if request is None:
            raise not_found("Registration request not found")
        if request.status != REGISTRATION_STATUS_PENDING:
            raise conflict("Only pending registration requests can be reviewed")
        return request

    def _ensure_identity_available(
        self,
        username_normalized: str,
        email_normalized: str | None,
        ignore_request_id: int | None = None,
    ) -> None:
        if self._users.get_user_by_username(username_normalized):
            raise conflict(UNAVAILABLE_MESSAGE)
        pending_username = self._requests.get_pending_by_username(username_normalized)
        if pending_username and pending_username.id != ignore_request_id:
            raise conflict(UNAVAILABLE_MESSAGE)
        if email_normalized:
            if self._users.get_user_by_email(email_normalized):
                raise conflict(UNAVAILABLE_MESSAGE)
            pending_email = self._requests.get_pending_by_email(email_normalized)
            if pending_email and pending_email.id != ignore_request_id:
                raise conflict(UNAVAILABLE_MESSAGE)

    def _check_rate_limits(self, ip_hash: str) -> None:
        hour_count = self._requests.count_recent_by_ip(ip_hash, hours=1)
        day_count = self._requests.count_recent_by_ip(ip_hash, hours=24)
        pending_count = self._requests.count_pending_by_ip(ip_hash)
        if (
            hour_count >= settings.registration_rate_limit_per_ip_per_hour
            or day_count >= settings.registration_rate_limit_per_ip_per_day
            or pending_count >= settings.registration_max_pending_per_ip
        ):
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "REGISTRATION_RATE_LIMITED",
                    "message": "Too many access requests. Try again later.",
                },
            )

    def _validate_username(self, username: str) -> str:
        clean = normalize_username(username)
        if not USERNAME_PATTERN.fullmatch(clean):
            raise bad_request(
                "Username must be 2-32 characters and use only letters, numbers, dot, underscore, or dash"
            )
        return clean

    def _validate_password(self, password: str) -> None:
        if not isinstance(password, str) or len(password) < 4 or len(password) > 64:
            raise bad_request("Password must be 4-64 characters")

    def _validate_email(self, email: str | None) -> str | None:
        clean = normalize_email(email)
        if clean is None:
            return None
        if len(clean) > 254 or not EMAIL_PATTERN.fullmatch(clean):
            raise bad_request("Email is invalid")
        return clean

    def _validate_message(self, message: str | None) -> str | None:
        if not isinstance(message, str):
            return None
        clean = message.strip()
        if not clean:
            return None
        if len(clean) > settings.registration_message_max_length:
            raise bad_request(
                f"Message must be at most {settings.registration_message_max_length} characters"
            )
        return clean

    def _validate_decision_reason(self, reason: str | None) -> str | None:
        clean = self._validate_message(reason)
        return clean


def registration_request_response(
    request: RegistrationRequestRecord,
) -> dict[str, Any]:
    return {
        "id": request.id,
        "username": request.username_normalized,
        "email": request.email_normalized,
        "message": request.message,
        "status": request.status,
        "requested_at": request.requested_at,
        "reviewed_at": request.reviewed_at,
        "reviewed_by_user_id": request.reviewed_by_user_id,
        "decision_reason": request.decision_reason,
        "request_ip_hash": request.request_ip_hash,
        "user_agent": request.user_agent,
        "created_at": request.created_at,
        "updated_at": request.updated_at,
    }
