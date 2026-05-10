from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.deps import require_admin
from app.infrastructure.audit_logs_repository import AuditLogsRepository
from app.infrastructure.security_repository import SecurityRepository
from app.infrastructure.users_repository import UserRecord

router = APIRouter(prefix="/admin/security", tags=["admin-security"])


@router.get("/login-attempts")
def login_attempts(
    limit: int = Query(default=100, ge=1, le=500),
    admin_user: UserRecord = Depends(require_admin),
):
    _ = admin_user
    return {"attempts": SecurityRepository().list_login_attempts(limit)}


@router.get("/blocked-logins")
def blocked_logins(admin_user: UserRecord = Depends(require_admin)):
    _ = admin_user
    return {
        "blocked": SecurityRepository().blocked_logins(
            window_minutes=settings.login_window_minutes,
            threshold=settings.login_max_failed_per_username,
        )
    }


@router.get("/audit-logs")
def audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    admin_user: UserRecord = Depends(require_admin),
):
    _ = admin_user
    return {"events": AuditLogsRepository().list_events(limit)}
