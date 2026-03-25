from __future__ import annotations

from app.core.exceptions import AllPlaylistItemsFailed, JobCanceled


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

    if "ffmpeg" in msg and ("not found" in msg or "no such file" in msg):
        return "FFMPEG_MISSING"

    if "http error 429" in msg or "too many requests" in msg:
        return "RATE_LIMITED"

    if "sign in" in msg or "login" in msg or "cookies" in msg:
        return "AUTH_REQUIRED"

    if "requested format is not available" in msg or "format not available" in msg:
        return "FORMAT_UNAVAILABLE"

    if "timed out" in msg or "timeout" in msg or "temporary failure" in msg:
        return "NETWORK"

    # YouTube-specific common cases (optional but useful).
    if "blocked it on copyright grounds" in msg:
        return "COPYRIGHT_BLOCKED"

    return "UPSTREAM_ERROR"
