from fastapi import APIRouter, Request

from app.core.errors import unauthorized
from app.core.security import create_access_token, verify_password
from app.core.users import USER_STATUS_ACTIVE
from app.infrastructure.users_repository import UsersRepository
from app.models.schemas import (
    LoginRequest,
    RegistrationRequestCreate,
    RegistrationRequestSubmitResponse,
    TokenResponse,
)
from app.services.login_protection import LoginProtectionService
from app.services.registration_requests_service import RegistrationRequestsService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request = None) -> TokenResponse:
    """Authenticate user and return JWT token."""
    repo = UsersRepository()
    protection = LoginProtectionService()
    protection.check_allowed(payload.username, request)

    user = repo.get_user_by_username(payload.username)
    if not user:
        protection.record_failure(payload.username, None, request, "invalid_credentials")
        raise unauthorized("Invalid username or password")

    if user.status != USER_STATUS_ACTIVE or user.deleted_at is not None:
        protection.record_failure(payload.username, user, request, "inactive_user")
        raise unauthorized("Invalid username or password")

    if not verify_password(payload.password, user.password_hash):
        protection.record_failure(payload.username, user, request, "invalid_credentials")
        raise unauthorized("Invalid username or password")

    repo.update_user_last_login(user.id)
    protection.record_success(user, request)
    token = create_access_token(
        subject=user.id,
        extra_claims={
            "username": user.username,
            "role": user.role,
            "token_version": user.token_version,
        },
    )
    return TokenResponse(access_token=token)


@router.post("/register-request", response_model=RegistrationRequestSubmitResponse)
def register_request(
    payload: RegistrationRequestCreate,
    request: Request = None,
) -> RegistrationRequestSubmitResponse:
    RegistrationRequestsService().submit_request(
        username=payload.username,
        password=payload.password,
        email=payload.email,
        message=payload.message,
        request=request,
    )
    return RegistrationRequestSubmitResponse()

