from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone


@dataclass
class JobLogger:
    path: Path

    def log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"{ts} | {message}\n")
