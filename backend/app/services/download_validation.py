from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


SUPPORTED_MODES = frozenset({"audio", "video"})
SUPPORTED_AUDIO_QUALITIES = frozenset({"best"})
SUPPORTED_VIDEO_QUALITY_HEIGHTS: dict[str, Optional[int]] = {
    "best": None,
    "144p": 144,
    "240p": 240,
    "360p": 360,
    "480p": 480,
    "720p": 720,
    "1080p": 1080,
    "1440p": 1440,
    "2160p": 2160,
}


@dataclass(frozen=True)
class DownloadOptions:
    url: str
    mode: str
    quality: str
    height: Optional[int]


def normalize_quality(quality: str) -> str:
    q = quality.strip().lower()
    if q.isdigit():
        q = f"{q}p"
    return q


def validate_download_request(url: str, mode: str, quality: str) -> DownloadOptions:
    clean_url = url.strip()
    clean_mode = mode.strip().lower()
    clean_quality = normalize_quality(quality)

    if clean_mode not in SUPPORTED_MODES:
        raise ValueError("Unsupported mode. Supported modes: audio, video")

    _validate_youtube_url(clean_url)

    if clean_mode == "audio":
        if clean_quality not in SUPPORTED_AUDIO_QUALITIES:
            raise ValueError("Audio mode supports only quality=best")
        return DownloadOptions(
            url=clean_url,
            mode=clean_mode,
            quality=clean_quality,
            height=None,
        )

    height = SUPPORTED_VIDEO_QUALITY_HEIGHTS.get(clean_quality)
    if clean_quality not in SUPPORTED_VIDEO_QUALITY_HEIGHTS:
        supported = ", ".join(SUPPORTED_VIDEO_QUALITY_HEIGHTS)
        raise ValueError(f"Unsupported quality. Supported video qualities: {supported}")

    return DownloadOptions(
        url=clean_url,
        mode=clean_mode,
        quality=clean_quality,
        height=height,
    )


def _validate_youtube_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Unsupported URL. Only YouTube URLs are supported")

    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        host == "youtu.be"
        or host == "youtube.com"
        or host.endswith(".youtube.com")
        or host == "youtube-nocookie.com"
        or host.endswith(".youtube-nocookie.com")
    ):
        return

    raise ValueError("Unsupported URL. Only YouTube URLs are supported")
