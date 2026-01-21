from __future__ import annotations
from pathlib import Path
from app.core.config import settings

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yt_dlp

from app.core.config import settings


@dataclass(frozen=True)
class ProcessResult:
    output_path: Path
    output_type: str  # "mp3" / "mp4" / "zip" / "mkv" / "webm"
    is_playlist: bool


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

        opts = {
            "outtmpl": outtmpl,
            "noplaylist": noplaylist,
            "restrictfilenames": False,  # Disable the aggressive ASCII-only filter
            "windowsfilenames": True,  # Enable smart Windows-compatible naming
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "ffmpeg_location": str(ffmpeg_bin),
            "writethumbnail": True,
            "convertthumbnails": "jpg",
        }

        # Thumbnail handling (needed for cover art)
        if settings.embed_thumbnail:
            opts["writethumbnail"] = (
                True  # download thumbnail file :contentReference[oaicite:3]{index=3}
            )
            # Convert thumbnail for better compatibility (webp -> jpg/png) :contentReference[oaicite:4]{index=4}
            opts["convertthumbnails"] = settings.thumbnail_convert_format

        return opts

    def _download_audio(
        self, url: str, out_dir: Path, is_playlist: bool
    ) -> ProcessResult:
        if is_playlist:
            outtmpl = str(out_dir / "%(playlist_index)s-%(title).200s.%(ext)s")
            noplaylist = False
        else:
            outtmpl = str(out_dir / "%(title).200s.%(ext)s")
            noplaylist = True

        opts = self._common_opts(outtmpl=outtmpl, noplaylist=noplaylist)
        opts["parse_metadata"] = self._parse_metadata_rules()
        # Best audio + convert to mp3 via FFmpeg
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "0",
                    },
                    # IMPORTANT: metadata first, then embed thumbnail :contentReference[oaicite:9]{index=9}
                    *self._metadata_postprocessors(),
                ],
            }
        )

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if is_playlist:
            zip_path = out_dir / "result.zip"
            self._zip_outputs(out_dir=out_dir, zip_path=zip_path, allowed_ext={".mp3"})
            return ProcessResult(
                output_path=zip_path, output_type="zip", is_playlist=True
            )

        fallback = self._pick_first(out_dir, exts={".mp3"})
        return ProcessResult(output_path=fallback, output_type="mp3", is_playlist=False)


    def _download_video(
        self, url: str, out_dir: Path, is_playlist: bool, height: Optional[int]
    ) -> ProcessResult:
        if is_playlist:
            outtmpl = str(out_dir / "%(playlist_index)s-%(title).200s.%(ext)s")
            noplaylist = False
        else:
            outtmpl = str(out_dir / "%(title).200s.%(ext)s")
            noplaylist = True

        # yt-dlp format selection examples: bv*+ba/b is canonical :contentReference[oaicite:3]{index=3}
        if height:
            fmt = f"bv*[height<={height}]+ba/b[height<={height}]"
        else:
            fmt = "bv*+ba/b"

        opts = self._common_opts(outtmpl=outtmpl, noplaylist=noplaylist)
        opts["parse_metadata"] = self._parse_metadata_rules()
        opts.update(
            {
                "format": fmt,
                "merge_output_format": "mp4",
                "postprocessors": [
                    *self._metadata_postprocessors(),
                ],
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
            return ProcessResult(
                output_path=zip_path, output_type="zip", is_playlist=True
            )

        fallback = self._pick_first(out_dir, exts={".mp4", ".mkv", ".webm"})
        return ProcessResult(output_path=fallback, output_type=fallback.suffix.lower().lstrip("."), is_playlist=False)


    def _zip_outputs(
        self, out_dir: Path, zip_path: Path, allowed_ext: set[str]
    ) -> None:
        if zip_path.exists():
            zip_path.unlink()

        # Remove temporary thumbnail files (jpg, webp, etc.) before zipping
        temp_exts = {".jpg", ".jpeg", ".png", ".webp"}
        for p in out_dir.iterdir():
            if p.is_file() and p.suffix.lower() in temp_exts:
                if p.suffix.lower() not in allowed_ext:
                    p.unlink()

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

    def _metadata_postprocessors(self) -> list[dict]:
        pps: list[dict] = []

        if settings.embed_metadata:
            # Adds/embeds metadata into the final media container :contentReference[oaicite:6]{index=6}
            pps.append({"key": "FFmpegMetadata", "add_metadata": True})

        if settings.embed_thumbnail:
            # Embed thumbnail as cover art :contentReference[oaicite:7]{index=7}
            pps.append({"key": "EmbedThumbnail"})

        return pps

    def _parse_metadata_rules(self) -> list[str]:
        return [
            # If title looks like "Artist - Title" parse it
            "title:%(artist)s - %(title)s",  # official example :contentReference[oaicite:6]{index=6}
            # Playlist mapping
            "playlist_title:%(album)s",
            "playlist_index:%(track_number)s",
            # Album artist fallback
            "uploader:%(album_artist)s",
        ]
