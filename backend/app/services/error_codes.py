from __future__ import annotations

from app.core.exceptions import AllPlaylistItemsFailed, JobCanceled


PERMANENT_ERROR_CODES = frozenset(
    {
        "ALL_ITEMS_FAILED",
        "AUTH_REQUIRED",
        "COPYRIGHT_BLOCKED",
        "FFMPEG_MISSING",
        "FORMAT_UNAVAILABLE",
        "INVALID_REQUEST",
        "PRIVATE_VIDEO",
        "UNSUPPORTED_URL",
        "VIDEO_UNAVAILABLE",
    }
)


def classify_error(exc: Exception) -> str:
    """Map exceptions to stable, frontend-friendly error codes."""
    # Handle explicit domain exceptions first (most reliable).
    if isinstance(exc, AllPlaylistItemsFailed):
        return "ALL_ITEMS_FAILED"
    if isinstance(exc, JobCanceled):
        return "CANCELED"

    msg = str(exc).lower()
    name = exc.__class__.__name__.lower()

    # Fallbacks in case the exception type isn't imported/propagated as expected.
    if name == "allplaylistitemsfailed" or "all playlist items failed" in msg:
        return "ALL_ITEMS_FAILED"

    if (
        isinstance(exc, ValueError)
        and (
            "unsupported mode" in msg
            or "unsupported quality" in msg
            or "audio mode supports only" in msg
        )
    ):
        return "INVALID_REQUEST"

    if "unsupported url" in msg or "only youtube urls are supported" in msg:
        return "UNSUPPORTED_URL"

    if "ffmpeg" in msg and ("not found" in msg or "no such file" in msg):
        return "FFMPEG_MISSING"

    if "http error 429" in msg or "too many requests" in msg:
        return "RATE_LIMITED"

    if "private video" in msg or "this video is private" in msg:
        return "PRIVATE_VIDEO"

    if "video unavailable" in msg or "this video is unavailable" in msg:
        return "VIDEO_UNAVAILABLE"

    if (
        "age-restricted" in msg
        or "age restricted" in msg
        or "confirm your age" in msg
        or "sign in" in msg
        or "login" in msg
        or "cookies" in msg
    ):
        return "AUTH_REQUIRED"

    if "requested format is not available" in msg or "format not available" in msg:
        return "FORMAT_UNAVAILABLE"

    if "timed out" in msg or "timeout" in msg or "temporary failure" in msg:
        return "NETWORK"

    # YouTube-specific common cases (optional but useful).
    if "blocked it on copyright grounds" in msg:
        return "COPYRIGHT_BLOCKED"

    return "UPSTREAM_ERROR"


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, JobCanceled):
        return False
    return classify_error(exc) not in PERMANENT_ERROR_CODES
