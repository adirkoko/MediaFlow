from __future__ import annotations

import hashlib

from fastapi import HTTPException, Request

from app.core.config import settings
from app.infrastructure.audit_logs_repository import AuditLogsRepository
from app.infrastructure.security_repository import SecurityRepository
from app.infrastructure.users_repository import UserRecord
from app.infrastructure.usage_repository import UsageEventInput
from app.services.usage_service import UsageService


def request_ip_hash(request: Request | None) -> str:
    host = "unknown"
    if request is not None and request.client is not None:
        host = request.client.host or "unknown"
    return hashlib.sha256(host.encode("utf-8")).hexdigest()


def request_user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent")


class LoginProtectionService:
    def __init__(self, repo: SecurityRepository | None = None) -> None:
        self._repo = repo or SecurityRepository()
        self._audit = AuditLogsRepository()
        self._usage = UsageService()

    def check_allowed(self, username: str, request: Request | None = None) -> None:
        ip_hash = request_ip_hash(request)
        window_minutes = max(settings.login_window_minutes, settings.login_block_minutes)
        username_failed = self._repo.count_failed_attempts(
            since_minutes=window_minutes,
            username=username,
        )
        ip_failed = self._repo.count_failed_attempts(
            since_minutes=window_minutes,
            ip_hash=ip_hash,
        )
        pair_failed = self._repo.count_failed_attempts(
            since_minutes=window_minutes,
            username=username,
            ip_hash=ip_hash,
        )
        if (
            username_failed >= settings.login_max_failed_per_username
            or ip_failed >= settings.login_max_failed_per_ip
            or pair_failed >= settings.login_max_failed_per_username
        ):
            self.record_failure(username, None, request, "login_blocked")
            self._usage.safe_record(
                UsageEventInput(
                    user_id="anonymous",
                    event_type="login_blocked",
                    status="blocked",
                    error_code="LOGIN_BLOCKED",
                    metadata={"username": username, "ip_hash": ip_hash},
                )
            )
            self._audit.add_event(
                actor_user_id="system",
                action="LOGIN_BLOCKED",
                target_type="login",
                target_id=username,
                metadata={"ip_hash": ip_hash, "window_minutes": window_minutes},
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "LOGIN_BLOCKED",
                    "message": "Too many failed login attempts. Try again later.",
                    "retry_after_minutes": settings.login_block_minutes,
                },
            )

    def record_success(self, user: UserRecord, request: Request | None = None) -> None:
        self._repo.record_login_attempt(
            username=user.username,
            user_id=user.id,
            ip_hash=request_ip_hash(request),
            user_agent=request_user_agent(request),
            success=True,
            failure_reason=None,
        )

    def record_failure(
        self,
        username: str,
        user: UserRecord | None,
        request: Request | None = None,
        reason: str = "invalid_credentials",
    ) -> None:
        self._repo.record_login_attempt(
            username=username,
            user_id=user.id if user else None,
            ip_hash=request_ip_hash(request),
            user_agent=request_user_agent(request),
            success=False,
            failure_reason=reason,
        )
        self._usage.safe_record(
            UsageEventInput(
                user_id=user.id if user else "anonymous",
                event_type="login_failed",
                status="failed",
                error_code=reason,
                metadata={"username": username, "ip_hash": request_ip_hash(request)},
            )
        )
