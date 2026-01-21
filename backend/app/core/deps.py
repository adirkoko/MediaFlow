from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.core.errors import unauthorized

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_username(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if not creds or creds.scheme.lower() != "bearer":
        raise unauthorized("Missing bearer token")

    payload = decode_access_token(creds.credentials)
    username = payload.get("sub")
    if not username:
        raise unauthorized("Invalid token")

    return str(username)
