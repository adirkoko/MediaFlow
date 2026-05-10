from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.users import USER_ROLE_USER  # noqa: E402
from app.infrastructure.db import ensure_db_initialized  # noqa: E402
from app.infrastructure.users_repository import UsersRepository  # noqa: E402


@dataclass(frozen=True)
class MigrationResult:
    inserted: int = 0
    skipped_existing: int = 0
    skipped_invalid: int = 0


def migrate_users_json_to_db(
    users_file: str | Path | None = None,
    db_path: str | Path | None = None,
) -> MigrationResult:
    original_db_path = settings.db_path
    if db_path is not None:
        settings.db_path = str(db_path)

    try:
        ensure_db_initialized()

        path = Path(users_file or settings.users_file)
        if not path.exists():
            raise FileNotFoundError(f"Users JSON file not found: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        raw_users = data.get("users", [])
        if not isinstance(raw_users, list):
            raise ValueError("Users JSON must contain a 'users' list")

        repo = UsersRepository()
        inserted = 0
        skipped_existing = 0
        skipped_invalid = 0

        for raw_user in raw_users:
            if not isinstance(raw_user, dict):
                skipped_invalid += 1
                continue

            username = str(raw_user.get("username") or "").strip()
            password_hash = str(raw_user.get("password_hash") or "")
            email_value = raw_user.get("email")
            email = str(email_value).strip() if email_value else None

            if not username or not password_hash:
                skipped_invalid += 1
                continue

            if repo.get_user_by_username(username):
                skipped_existing += 1
                continue

            repo.create_user(
                username=username,
                password_hash=password_hash,
                email=email,
                role=USER_ROLE_USER,
            )
            inserted += 1

        return MigrationResult(
            inserted=inserted,
            skipped_existing=skipped_existing,
            skipped_invalid=skipped_invalid,
        )
    finally:
        settings.db_path = original_db_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate legacy users.json entries into the MediaFlow users table."
    )
    parser.add_argument(
        "--users-file",
        default=None,
        help="Path to users.json. Defaults to USERS_FILE from the backend config.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to SQLite DB. Defaults to DB_PATH from the backend config.",
    )
    args = parser.parse_args()

    result = migrate_users_json_to_db(
        users_file=args.users_file,
        db_path=args.db_path,
    )
    print(
        "Migration complete: "
        f"inserted={result.inserted} "
        f"skipped_existing={result.skipped_existing} "
        f"skipped_invalid={result.skipped_invalid}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
