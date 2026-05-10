import re

REGISTRATION_STATUS_PENDING = "pending"
REGISTRATION_STATUS_APPROVED = "approved"
REGISTRATION_STATUS_REJECTED = "rejected"

ALLOWED_REGISTRATION_STATUSES = frozenset(
    {
        REGISTRATION_STATUS_PENDING,
        REGISTRATION_STATUS_APPROVED,
        REGISTRATION_STATUS_REJECTED,
    }
)

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{2,32}$")


def normalize_username(username: str) -> str:
    return username.strip().lower()


def normalize_email(email: str | None) -> str | None:
    if not isinstance(email, str):
        return None
    clean = email.strip().lower()
    return clean or None
