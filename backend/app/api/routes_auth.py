from fastapi import APIRouter

from app.core.errors import unauthorized
from app.core.security import create_access_token, verify_password
from app.core.users import USER_STATUS_ACTIVE
from app.infrastructure.users_repository import UsersRepository
from app.models.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    """Authenticate user and return JWT token."""
    repo = UsersRepository()
    user = repo.get_user_by_username(payload.username)
    if not user:
        raise unauthorized("User not found")

    if user.status != USER_STATUS_ACTIVE or user.deleted_at is not None:
        raise unauthorized("User is not active")

    if not verify_password(payload.password, user.password_hash):
        raise unauthorized("Incorrect password")

    repo.update_user_last_login(user.id)
    token = create_access_token(
        subject=user.id,
        extra_claims={
            "username": user.username,
            "role": user.role,
            "token_version": user.token_version,
        },
    )
    return TokenResponse(access_token=token)

