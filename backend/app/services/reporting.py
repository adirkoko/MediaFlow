from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class PlaylistFailure:
    index: int
    title: str | None
    video_id: str | None
    url: str | None
    reason_code: str
    error_message: str


@dataclass
class PlaylistReport:
    job_id: str
    source_url: str
    mode: str
    quality: str
    total_items: int
    succeeded: int
    failed: int
    success_files: list[str]
    failures: list[PlaylistFailure]


class ReportWriter:
    def write_playlist_report(self, out_dir: Path, report: PlaylistReport) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "report.json"
        payload = asdict(report)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return p
