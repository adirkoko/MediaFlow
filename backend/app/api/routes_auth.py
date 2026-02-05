from fastapi import APIRouter
import os

from app.core.errors import unauthorized
from app.core.security import create_access_token, verify_password
from app.infrastructure.users_store import UsersStore
from app.models.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    """Authenticate user and return JWT token."""
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password_hash = os.getenv("ADMIN_PASSWORD_HASH")

    # Check admin credentials from env vars first 
    if admin_username and admin_password_hash:
        if payload.username != admin_username:
            raise unauthorized("User not found")

        if not verify_password(payload.password, admin_password_hash):
            raise unauthorized("Incorrect password")

        token = create_access_token(subject=admin_username)
        return TokenResponse(access_token=token)

    # Fallback to users store if no admin creds are set in env vars 
    store = UsersStore()
    user = store.get_user(payload.username)
    if not user:
        raise unauthorized("User not found")

    if not verify_password(payload.password, user.password_hash):
        raise unauthorized("Incorrect password")

    token = create_access_token(subject=user.username)
    return TokenResponse(access_token=token)

