from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_admin
from app.infrastructure.users_repository import UserRecord
from app.services.usage_service import UsageService

router = APIRouter(prefix="/admin/usage", tags=["admin-usage"])


@router.get("/summary")
def admin_usage_summary(
    range: str = "today",
    admin_user: UserRecord = Depends(require_admin),
):
    _ = admin_user
    return {"range": range, "summary": UsageService().get_admin_usage_summary(range)}


@router.get("/users")
def admin_usage_users(
    range: str = "today",
    limit: int = Query(default=50, ge=1, le=200),
    admin_user: UserRecord = Depends(require_admin),
):
    _ = admin_user
    return {"range": range, "users": UsageService().get_heavy_users(range, limit)}


@router.get("/users/{user_id}")
def admin_usage_user(
    user_id: str,
    range: str = "today",
    admin_user: UserRecord = Depends(require_admin),
):
    _ = admin_user
    return {"range": range, "user_id": user_id, "summary": UsageService().get_user_usage_summary(user_id, range)}


@router.get("/users/{user_id}/daily")
def admin_usage_user_daily(
    user_id: str,
    days: int = Query(default=30, ge=1, le=365),
    admin_user: UserRecord = Depends(require_admin),
):
    _ = admin_user
    return {"user_id": user_id, "days": days, "daily": UsageService().get_user_daily_usage(user_id, days)}


@router.get("/heavy-users")
def admin_heavy_users(
    range: str = "today",
    limit: int = Query(default=20, ge=1, le=100),
    admin_user: UserRecord = Depends(require_admin),
):
    _ = admin_user
    return {"range": range, "users": UsageService().get_heavy_users(range, limit)}


@router.get("/quota-exceeded")
def admin_quota_exceeded(
    range: str = "today",
    limit: int = Query(default=100, ge=1, le=500),
    admin_user: UserRecord = Depends(require_admin),
):
    _ = admin_user
    return {"range": range, "events": UsageService().list_quota_exceeded(range, limit)}
