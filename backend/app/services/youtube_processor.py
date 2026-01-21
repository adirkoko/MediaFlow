from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp

from app.core.config import settings


@dataclass(frozen=True)
class ProcessResult:
    output_path: Path
    is_archive: bool


def _parse_quality_to_height(quality: str) -> Optional[int]:
    """
    Accepts values like: "best", "720p", "1080", "480p"
    Returns height (int) or None.
    """
    q = quality.strip().lower().replace("p", "")
    if q == "best":
        return None
    if q.isdigit():
        return int(q)
    return None


class YouTubeProcessor:
    def process(self, job_id: str, url: str, mode: str, quality: str) -> ProcessResult:
        out_dir = Path(settings.outputs_dir) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # Detect playlist vs single (so we can decide zip vs single fixed output name)
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)

        is_playlist = bool(
            info and (info.get("_type") == "playlist" or info.get("entries"))
        )
        height = _parse_quality_to_height(quality)

        if mode == "audio":
            return self._download_audio(
                url=url, out_dir=out_dir, is_playlist=is_playlist
            )
        if mode == "video":
            return self._download_video(
                url=url, out_dir=out_dir, is_playlist=is_playlist, height=height
            )

        raise ValueError(f"Unsupported mode: {mode}")

    def _common_opts(self, outtmpl: str, noplaylist: bool) -> dict:
        ffmpeg_bin = Path.cwd() / "bin" / "ffmpeg.exe"

        # --restrict-filenames is recommended when moving to Windows filesystems / unsafe channels :contentReference[oaicite:2]{index=2}
        return {
            "outtmpl": outtmpl,
            "noplaylist": noplaylist,
            "restrictfilenames": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "ffmpeg_location": str(ffmpeg_bin),
        }

    def _download_audio(
        self, url: str, out_dir: Path, is_playlist: bool
    ) -> ProcessResult:
        if is_playlist:
            outtmpl = str(out_dir / "%(playlist_index)s-%(title).200s.%(ext)s")
            noplaylist = False
        else:
            outtmpl = str(out_dir / "result.%(ext)s")
            noplaylist = True

        opts = self._common_opts(outtmpl=outtmpl, noplaylist=noplaylist)
        # Best audio + convert to mp3 via FFmpeg
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "0",
                    }
                ],
            }
        )

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if is_playlist:
            zip_path = out_dir / "result.zip"
            self._zip_outputs(out_dir=out_dir, zip_path=zip_path, allowed_ext={".mp3"})
            return ProcessResult(output_path=zip_path, is_archive=True)

        mp3_path = out_dir / "result.mp3"
        if mp3_path.exists():
            return ProcessResult(output_path=mp3_path, is_archive=False)

        # Fallback: pick first mp3
        fallback = self._pick_first(out_dir, exts={".mp3"})
        return ProcessResult(output_path=fallback, is_archive=False)

    def _download_video(
        self, url: str, out_dir: Path, is_playlist: bool, height: Optional[int]
    ) -> ProcessResult:
        if is_playlist:
            outtmpl = str(out_dir / "%(playlist_index)s-%(title).200s.%(ext)s")
            noplaylist = False
        else:
            outtmpl = str(out_dir / "result.%(ext)s")
            noplaylist = True

        # yt-dlp format selection examples: bv*+ba/b is canonical :contentReference[oaicite:3]{index=3}
        if height:
            fmt = f"bv*[height<={height}]+ba/b[height<={height}]"
        else:
            fmt = "bv*+ba/b"

        opts = self._common_opts(outtmpl=outtmpl, noplaylist=noplaylist)
        opts.update(
            {
                "format": fmt,
                "merge_output_format": "mp4",
            }
        )

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if is_playlist:
            zip_path = out_dir / "result.zip"
            self._zip_outputs(
                out_dir=out_dir,
                zip_path=zip_path,
                allowed_ext={".mp4", ".mkv", ".webm"},
            )
            return ProcessResult(output_path=zip_path, is_archive=True)

        # Prefer mp4; sometimes merge may produce mkv if mp4 not feasible
        for name in ("result.mp4", "result.mkv", "result.webm"):
            p = out_dir / name
            if p.exists():
                return ProcessResult(output_path=p, is_archive=False)

        fallback = self._pick_first(out_dir, exts={".mp4", ".mkv", ".webm"})
        return ProcessResult(output_path=fallback, is_archive=False)

    def _zip_outputs(
        self, out_dir: Path, zip_path: Path, allowed_ext: set[str]
    ) -> None:
        if zip_path.exists():
            zip_path.unlink()

        files = [
            p
            for p in out_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in allowed_ext
            and p.name != zip_path.name
        ]

        if not files:
            raise RuntimeError("No output files to zip")

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in files:
                zf.write(p, arcname=p.name)

    def _pick_first(self, out_dir: Path, exts: set[str]) -> Path:
        for p in out_dir.iterdir():
            if p.is_file() and p.suffix.lower() in exts:
                return p
        raise RuntimeError("No output file produced")
