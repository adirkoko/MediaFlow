from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import require_admin
from app.core.errors import bad_request
from app.infrastructure.audit_logs_repository import AuditLogsRepository
from app.infrastructure.quotas_repository import QuotasRepository
from app.infrastructure.users_repository import UserRecord, UsersRepository
from app.models.schemas import QuotaUpdateRequest, RoleQuotaResponse, UserQuotaResponse
from app.services.quota_service import QuotaService, validate_quota_updates

router = APIRouter(prefix="/admin", tags=["admin-quotas"])


@router.get("/quotas/roles", response_model=list[RoleQuotaResponse])
def list_role_quotas(admin_user: UserRecord = Depends(require_admin)):
    _ = admin_user
    return [
        RoleQuotaResponse(
            role=row.role,
            quota=row.quota.to_dict(),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in QuotasRepository().list_role_quotas()
    ]


@router.get("/quotas/roles/{role}", response_model=RoleQuotaResponse)
def get_role_quota(role: str, admin_user: UserRecord = Depends(require_admin)):
    _ = admin_user
    row = QuotasRepository().get_role_quota(role)
    return RoleQuotaResponse(
        role=row.role,
        quota=row.quota.to_dict(),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.patch("/quotas/roles/{role}", response_model=RoleQuotaResponse)
def patch_role_quota(
    role: str,
    payload: QuotaUpdateRequest,
    admin_user: UserRecord = Depends(require_admin),
):
    updates = validate_quota_updates(payload.model_dump(exclude_unset=True))
    if any(value is None for value in updates.values()):
        raise bad_request("Role quota fields cannot be null")
    row = QuotasRepository().update_role_quota(role, updates)
    AuditLogsRepository().add_event(
        actor_user_id=admin_user.id,
        action="ROLE_QUOTA_UPDATED",
        target_type="role_quota",
        target_id=role,
        metadata={"fields": sorted(updates)},
    )
    return RoleQuotaResponse(
        role=row.role,
        quota=row.quota.to_dict(),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/users/{user_id}/quota", response_model=UserQuotaResponse)
def get_user_quota(user_id: str, admin_user: UserRecord = Depends(require_admin)):
    _ = admin_user
    user = UsersRepository().get_user_by_id(user_id)
    if not user:
        from app.core.errors import not_found

        raise not_found("User not found")
    repo = QuotasRepository()
    override = repo.get_user_quota(user.id)
    effective = QuotaService(repo).get_effective_quota(user)
    return UserQuotaResponse(
        user_id=user.id,
        role=user.role,
        effective_quota=effective.to_dict(),
        override_quota=override.quota.to_dict() if override else None,
    )


@router.patch("/users/{user_id}/quota", response_model=UserQuotaResponse)
def patch_user_quota(
    user_id: str,
    payload: QuotaUpdateRequest,
    admin_user: UserRecord = Depends(require_admin),
):
    user = UsersRepository().get_user_by_id(user_id)
    if not user:
        from app.core.errors import not_found

        raise not_found("User not found")
    updates = validate_quota_updates(payload.model_dump(exclude_unset=True))
    repo = QuotasRepository()
    repo.upsert_user_quota(user.id, updates)
    AuditLogsRepository().add_event(
        actor_user_id=admin_user.id,
        action="USER_QUOTA_UPDATED",
        target_type="user",
        target_id=user.id,
        metadata={"fields": sorted(updates)},
    )
    return get_user_quota(user.id, admin_user)


@router.delete("/users/{user_id}/quota", response_model=UserQuotaResponse)
def delete_user_quota(user_id: str, admin_user: UserRecord = Depends(require_admin)):
    user = UsersRepository().get_user_by_id(user_id)
    if not user:
        from app.core.errors import not_found

        raise not_found("User not found")
    QuotasRepository().delete_user_quota(user.id)
    AuditLogsRepository().add_event(
        actor_user_id=admin_user.id,
        action="USER_QUOTA_DELETED",
        target_type="user",
        target_id=user.id,
        metadata={},
    )
    return get_user_quota(user.id, admin_user)
