import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core.config import settings


@dataclass(frozen=True)
class User:
    username: str
    password_hash: str


class UsersStore:
    def __init__(self, users_file: str | None = None) -> None:
        self._path = Path(users_file or settings.users_file)

    def get_user(self, username: str) -> Optional[User]:
        if not self._path.exists():
            return None

        data = json.loads(self._path.read_text(encoding="utf-8"))
        # expected: {"users": [{"username": "...", "password_hash": "..."}]}
        for u in data.get("users", []):
            if u.get("username") == username:
                return User(username=u["username"], password_hash=u["password_hash"])
        return None
