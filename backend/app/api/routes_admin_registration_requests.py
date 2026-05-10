from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.core.deps import require_admin
from app.infrastructure.users_repository import UserRecord
from app.models.schemas import (
    AdminRegistrationRequestResponse,
    AdminRejectRegistrationRequest,
    AdminUserResponse,
)
from app.services.registration_requests_service import (
    RegistrationRequestsService,
    registration_request_response,
)

router = APIRouter(
    prefix="/admin/registration-requests",
    tags=["admin-registration-requests"],
)


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


@router.get("", response_model=list[AdminRegistrationRequestResponse])
def list_registration_requests(
    status: str | None = "pending",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin_user: UserRecord = Depends(require_admin),
) -> list[AdminRegistrationRequestResponse]:
    _ = admin_user
    requests = RegistrationRequestsService().list_requests(
        status=status,
        limit=limit,
        offset=offset,
    )
    return [AdminRegistrationRequestResponse(**registration_request_response(r)) for r in requests]


@router.post("/{request_id}/approve", response_model=AdminUserResponse)
def approve_registration_request(
    request_id: int,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminUserResponse:
    user = RegistrationRequestsService().approve_request(admin_user, request_id)
    return _user_response(user)


@router.post("/{request_id}/reject", response_model=AdminRegistrationRequestResponse)
def reject_registration_request(
    request_id: int,
    payload: AdminRejectRegistrationRequest | None = None,
    admin_user: UserRecord = Depends(require_admin),
) -> AdminRegistrationRequestResponse:
    request = RegistrationRequestsService().reject_request(
        actor=admin_user,
        request_id=request_id,
        reason=payload.reason if payload else None,
    )
    return AdminRegistrationRequestResponse(**registration_request_response(request))
