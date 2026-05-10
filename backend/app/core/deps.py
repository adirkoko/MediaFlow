from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.core.errors import forbidden, unauthorized
from app.core.users import USER_ROLE_ADMIN, USER_STATUS_ACTIVE
from app.infrastructure.users_repository import UserRecord, UsersRepository

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserRecord:
    if not creds or creds.scheme.lower() != "bearer":
        raise unauthorized("Missing bearer token")

    payload = decode_access_token(creds.credentials)
    user_id = payload.get("sub")
    token_version = payload.get("token_version")
    if not user_id:
        raise unauthorized("Invalid token")
    if token_version is None:
        raise unauthorized("Invalid token")

    user = UsersRepository().get_user_by_id(str(user_id))
    if not user:
        raise unauthorized("Invalid token")
    if user.status != USER_STATUS_ACTIVE or user.deleted_at is not None:
        raise unauthorized("User is not active")
    try:
        token_version_value = int(token_version)
    except (TypeError, ValueError):
        raise unauthorized("Invalid token")

    if token_version_value != int(user.token_version):
        raise unauthorized("Invalid token")

    return user


def get_current_username(current_user: UserRecord = Depends(get_current_user)) -> str:
    return current_user.username


def get_current_admin_user(
    current_user: UserRecord = Depends(get_current_user),
) -> UserRecord:
    return require_admin(current_user)


def require_admin(current_user: UserRecord = Depends(get_current_user)) -> UserRecord:
    if current_user.role != USER_ROLE_ADMIN:
        raise forbidden("Admin privileges required")
    return current_user
