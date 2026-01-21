from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class BackoffConfig:
    max_attempts: int
    base_delay_seconds: float


def run_with_backoff(fn: Callable[[], T], cfg: BackoffConfig) -> T:
    attempts = max(1, cfg.max_attempts)
    base = max(0.1, cfg.base_delay_seconds)

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt == attempts:
                raise
            # Exponential backoff + small jitter
            delay = base * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            time.sleep(delay)

    # should not get here
    assert last_exc is not None
    raise last_exc
