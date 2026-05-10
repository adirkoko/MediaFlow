from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        events = self._events[key]
        cutoff = now - window_seconds
        while events and events[0] < cutoff:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "RATE_LIMITED",
                    "message": "Too many requests. Try again later.",
                    "limit": limit,
                    "window_seconds": window_seconds,
                },
            )
        events.append(now)

    def clear(self) -> None:
        self._events.clear()


rate_limiter = InMemoryRateLimiter()
