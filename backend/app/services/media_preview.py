from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import yt_dlp

from app.core.config import settings
from app.services.cookies import prepare_job_cookies
from app.services.download_validation import (
    SUPPORTED_VIDEO_QUALITY_HEIGHTS,
    validate_youtube_url,
)
from app.services.youtube_processor import YouTubeProcessor


@dataclass(frozen=True)
class VideoQualityPreview:
    quality: str
    height: int | None
    ext: str | None = None
    filesize_bytes: int | None = None
    fps: float | None = None
    vcodec: str | None = None
    acodec: str | None = None


@dataclass(frozen=True)
class MediaPreview:
    url: str
    webpage_url: str | None
    title: str
    thumbnail: str | None
    uploader: str | None
    duration_seconds: int | None
    is_playlist: bool
    playlist_count: int | None
    audio_ext: str | None
    audio_filesize_bytes: int | None
    video_qualities: list[VideoQualityPreview]


class MediaPreviewer:
    def __init__(self) -> None:
        self._processor = YouTubeProcessor()

    def preview(self, url: str) -> MediaPreview:
        clean_url = validate_youtube_url(url)
        cookies_handle = prepare_job_cookies(settings.cookies_file, f"preview_{uuid4().hex}")

        try:
            opts = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": False,
                **self._processor._youtube_runtime_opts(),
            }
            if cookies_handle:
                opts["cookiefile"] = str(cookies_handle.path)

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = self._extract_preview_info(ydl, clean_url)
        finally:
            if cookies_handle:
                cookies_handle.cleanup()

        is_playlist = self._is_playlist_info(info)
        entries = [e for e in (info.get("entries") or []) if e]
        formats = info.get("formats") or []

        return MediaPreview(
            url=clean_url,
            webpage_url=info.get("webpage_url"),
            title=info.get("title") or "Untitled",
            thumbnail=self._best_thumbnail(info),
            uploader=info.get("uploader") or info.get("channel"),
            duration_seconds=self._int_or_none(info.get("duration")),
            is_playlist=is_playlist,
            playlist_count=self._playlist_count(info, entries),
            audio_ext=self._best_audio_ext(formats),
            audio_filesize_bytes=self._best_audio_size(formats),
            video_qualities=self._video_qualities(formats),
        )

    def _extract_preview_info(self, ydl: yt_dlp.YoutubeDL, url: str) -> dict[str, Any]:
        probe = ydl.extract_info(url, download=False, process=False)
        if not isinstance(probe, dict):
            raise ValueError("Could not read media preview")
        if self._is_playlist_info(probe):
            return probe

        info = ydl.extract_info(url, download=False)
        if not isinstance(info, dict):
            raise ValueError("Could not read media preview")
        return info

    def _is_playlist_info(self, info: dict[str, Any]) -> bool:
        return bool(info.get("_type") == "playlist" or info.get("entries"))

    def _playlist_count(self, info: dict[str, Any], entries: list[dict]) -> int | None:
        for key in ("playlist_count", "n_entries"):
            value = info.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        return len(entries) if entries else None

    def _best_thumbnail(self, info: dict[str, Any]) -> str | None:
        thumbnails = info.get("thumbnails") or []
        if isinstance(thumbnails, list) and thumbnails:
            best = max(
                (t for t in thumbnails if isinstance(t, dict) and t.get("url")),
                key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
                default=None,
            )
            if best:
                return best.get("url")
        thumb = info.get("thumbnail")
        return thumb if isinstance(thumb, str) and thumb else None

    def _best_audio_ext(self, formats: list[dict]) -> str | None:
        best = self._best_audio_format(formats)
        return best.get("ext") if best else None

    def _best_audio_size(self, formats: list[dict]) -> int | None:
        best = self._best_audio_format(formats)
        return self._filesize(best) if best else None

    def _best_audio_format(self, formats: list[dict]) -> dict | None:
        audio_formats = [
            f
            for f in formats
            if f.get("acodec") not in (None, "none")
            and f.get("vcodec") in (None, "none")
        ]
        if not audio_formats:
            return None
        return max(audio_formats, key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0))

    def _video_qualities(self, formats: list[dict]) -> list[VideoQualityPreview]:
        by_height: dict[int, dict] = {}
        for fmt in formats:
            height = fmt.get("height")
            if not isinstance(height, int):
                continue
            if fmt.get("vcodec") in (None, "none"):
                continue
            existing = by_height.get(height)
            if existing is None or self._format_score(fmt) > self._format_score(existing):
                by_height[height] = fmt

        audio_size = self._best_audio_size(formats)
        previews: list[VideoQualityPreview] = []
        for quality, height in SUPPORTED_VIDEO_QUALITY_HEIGHTS.items():
            if height is None:
                continue
            fmt = by_height.get(height)
            if not fmt:
                continue
            video_size = self._filesize(fmt)
            previews.append(
                VideoQualityPreview(
                    quality=quality,
                    height=height,
                    ext=fmt.get("ext"),
                    filesize_bytes=self._combined_size(video_size, audio_size),
                    fps=fmt.get("fps"),
                    vcodec=fmt.get("vcodec"),
                    acodec=fmt.get("acodec"),
                )
            )

        if previews:
            best = max(previews, key=lambda q: q.height or 0)
            previews.insert(
                0,
                VideoQualityPreview(
                    quality="best",
                    height=best.height,
                    ext=best.ext,
                    filesize_bytes=best.filesize_bytes,
                    fps=best.fps,
                    vcodec=best.vcodec,
                    acodec=best.acodec,
                ),
            )

        return previews

    def _format_score(self, fmt: dict) -> tuple[int, float, int]:
        is_mp4 = 1 if fmt.get("ext") == "mp4" else 0
        tbr = float(fmt.get("tbr") or 0)
        size = self._filesize(fmt) or 0
        return is_mp4, tbr, size

    def _combined_size(self, video_size: int | None, audio_size: int | None) -> int | None:
        if video_size is None:
            return None
        return video_size + (audio_size or 0)

    def _filesize(self, fmt: dict | None) -> int | None:
        if not fmt:
            return None
        value = fmt.get("filesize") or fmt.get("filesize_approx")
        return self._int_or_none(value)

    def _int_or_none(self, value) -> int | None:
        if isinstance(value, (int, float)) and value >= 0:
            return int(value)
        return None
