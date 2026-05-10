from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status as http_status

from app.core.deps import require_admin
from app.infrastructure.users_repository import UserRecord
from app.models.schemas import (
    AdminCreateUserRequest,
    AdminResetPasswordRequest,
    AdminUpdateUserRequest,
    AdminUserResponse,
)
from app.services.admin_users_service import AdminUsersService

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _service() -> AdminUsersService:
    return AdminUsersService()


def _user_response(user: UserRecord) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        status=user.status,
        token_version=user.token_version,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        deleted_at=user.deleted_at,
    )


@router.get("", response_model=list[AdminUserResponse])
def list_admin_users(
    status: str | None = None,
    role: str | None = None,
    search: str | None = None,
    include_deleted: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin_user: UserRecord = Depends(require_admin),
) -> list[AdminUserResponse]:
    users = _service().list_users(
        status=status,
        role=role,
        search=search,
        include_deleted=include_deleted,
        limit=limit,
        offset=offset,
    )
    return [_user_response(user) for user in users]


@router.post(
    "",
    response_model=AdminUserResponse,
    status_code=http_status.HTTP_201_CREATED,
)
def create_admin_user(
    payload: AdminCreateUserRequest,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    user = _service().create_user(
        actor=admin_user,
        username=payload.username,
        password=payload.password,
        email=payload.email,
        role=payload.role,
        status=payload.status,
    )
    return _user_response(user)


@router.get("/{user_id}", response_model=AdminUserResponse)
def get_admin_user(
    user_id: str,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    _ = admin_user
    return _user_response(_service().get_user(user_id))


@router.patch("/{user_id}", response_model=AdminUserResponse)
def patch_admin_user(
    user_id: str,
    payload: AdminUpdateUserRequest,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    user = _service().update_user(
        actor=admin_user,
        user_id=user_id,
        fields=payload.model_dump(exclude_unset=True),
    )
    return _user_response(user)


@router.post("/{user_id}/disable", response_model=AdminUserResponse)
def disable_admin_user(
    user_id: str,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    return _user_response(_service().disable_user(admin_user, user_id))


@router.post("/{user_id}/enable", response_model=AdminUserResponse)
def enable_admin_user(
    user_id: str,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    return _user_response(_service().enable_user(admin_user, user_id))


@router.post("/{user_id}/soft-delete", response_model=AdminUserResponse)
def soft_delete_admin_user(
    user_id: str,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    return _user_response(_service().soft_delete_user(admin_user, user_id))


@router.post("/{user_id}/reset-password", response_model=AdminUserResponse)
def reset_admin_user_password(
    user_id: str,
    payload: AdminResetPasswordRequest,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    return _user_response(
        _service().reset_user_password(admin_user, user_id, payload.new_password)
    )


@router.post("/{user_id}/revoke-tokens", response_model=AdminUserResponse)
def revoke_admin_user_tokens(
    user_id: str,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    return _user_response(_service().revoke_user_tokens(admin_user, user_id))
