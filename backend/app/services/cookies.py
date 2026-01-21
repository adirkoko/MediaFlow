from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CookiesHandle:
    path: Path

    def cleanup(self) -> None:
        try:
            if self.path.exists():
                self.path.unlink()
        except Exception:
            pass


def prepare_job_cookies(source_path: str | None, job_id: str) -> CookiesHandle | None:
    if not source_path:
        return None

    src = Path(source_path)
    if not src.exists() or not src.is_file():
        return None

    # Copy to a temp per-job file, so we can delete after finishing.
    tmp_dir = Path(tempfile.gettempdir()) / "mediaflow_cookies"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    dst = tmp_dir / f"cookies_{job_id}.txt"
    shutil.copyfile(src, dst)

    # Ensure it's not world-readable in unix-like envs (harmless on Windows)
    try:
        os.chmod(dst, 0o600)
    except Exception:
        pass

    return CookiesHandle(path=dst)
