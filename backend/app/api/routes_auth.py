from fastapi import APIRouter

from app.core.errors import unauthorized
from app.core.security import create_access_token, verify_password
from app.infrastructure.users_store import UsersStore
from app.models.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    store = UsersStore()
    user = store.get_user(payload.username)
    if not user:
        raise unauthorized("User not found")

    if not verify_password(payload.password, user.password_hash):
        raise unauthorized("Incorrect password")

    token = create_access_token(subject=user.username)
    return TokenResponse(access_token=token)
