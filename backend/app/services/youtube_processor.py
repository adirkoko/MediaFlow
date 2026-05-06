from __future__ import annotations

import yt_dlp
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core.config import settings
from app.services.packaging import OutputPackager
from app.services.reporting import ReportWriter, PlaylistReport, PlaylistFailure
from app.core.exceptions import AllPlaylistItemsFailed, JobCanceled
from app.services.error_codes import classify_error  # reuse your classifier


@dataclass(frozen=True)
class ProcessResult:
    output_path: Path
    output_type: str  # "mp3" / "mp4" / "zip" / "mkv" / "webm"
    is_playlist: bool
    playlist_total: Optional[int] = None
    playlist_succeeded: Optional[int] = None
    playlist_failed: Optional[int] = None


def _parse_quality_to_height(quality: str) -> Optional[int]:
    """
    Accepts values like: "best", "720p", "1080", "480p".
    Returns height (int) or None (for best).
    """
    q = quality.strip().lower().replace("p", "")
    if q == "best":
        return None
    if q.isdigit():
        return int(q)
    return None


class YouTubeProcessor:
    def __init__(self) -> None:
        # Packaging (zip + output selection) is delegated to a focused helper.
        self._packager = OutputPackager()
        self._packager = OutputPackager()
        self._reporter = ReportWriter()

    def process(
        self,
        job_id: str,
        url: str,
        mode: str,
        quality: str,
        cookies_path: str | None = None,
        progress_cb: (
            Callable[[Optional[int], str, Optional[int], Optional[int]], None] | None
        ) = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ProcessResult:
        self._ensure_not_canceled(should_cancel)
        out_dir = Path(settings.outputs_dir) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1) Safe detect: avoid processing playlist entries during probing
        probe_opts = {"quiet": True, "no_warnings": True, **self._youtube_runtime_opts()}
        if cookies_path:
            probe_opts["cookiefile"] = cookies_path

        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            self._ensure_not_canceled(should_cancel)
            info = ydl.extract_info(url, download=False, process=False)

        is_playlist = bool(
            info and (info.get("_type") == "playlist" or info.get("entries"))
        )
        height = _parse_quality_to_height(quality)

        # 2) Playlist path: process item-by-item and return ZIP (do NOT call _download_audio/_download_video)
        if is_playlist:
            return self._process_playlist(
                job_id=job_id,
                playlist_url=url,
                mode=mode,
                quality=quality,
                height=height,
                out_dir=out_dir,
                cookies_path=cookies_path,
                progress_cb=progress_cb,
                should_cancel=should_cancel,
            )

        # Single item path: now we can extract full info (safe to decide split_title)
        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            self._ensure_not_canceled(should_cancel)
            full_info = ydl.extract_info(url, download=False)

        split_title = self._should_split_title(full_info or {}, url, is_playlist=False)

        if mode == "audio":
            return self._download_audio(
                url=url,
                out_dir=out_dir,
                is_playlist=False,
                split_title=split_title,
                cookies_path=cookies_path,
                progress_cb=progress_cb,
                should_cancel=should_cancel,
            )

        if mode == "video":
            return self._download_video(
                url=url,
                out_dir=out_dir,
                is_playlist=False,
                height=height,
                split_title=split_title,
                cookies_path=cookies_path,
                progress_cb=progress_cb,
                should_cancel=should_cancel,
            )

        raise ValueError(f"Unsupported mode: {mode}")

    def _common_opts(
        self,
        outtmpl: str,
        noplaylist: bool,
        cookies_path: str | None,
        progress_hook=None,
    ) -> dict:
        # On Windows, we keep a repo-local FFmpeg binary path for predictability.
        ffmpeg_bin = Path.cwd() / "bin" / "ffmpeg.exe"

        opts = {
            "outtmpl": outtmpl,
            "noplaylist": noplaylist,
            "windowsfilenames": True,
            "restrictfilenames": False,
            "quiet": True,
            "no_warnings": True,
            "retries": settings.ytdlp_retries,
            "fragment_retries": settings.ytdlp_fragment_retries,
            "extractor_retries": settings.ytdlp_extractor_retries,
            **self._youtube_runtime_opts(),
        }

        if ffmpeg_bin.exists():
            opts["ffmpeg_location"] = str(ffmpeg_bin)

        if cookies_path:
            # Optional: authenticated access (age-gated/private/unlisted where applicable).
            opts["cookiefile"] = cookies_path

        if settings.embed_thumbnail:
            # Download thumbnail and convert to a stable format for embedding.
            opts["writethumbnail"] = True
            opts["convertthumbnails"] = settings.thumbnail_convert_format

        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        return opts

    def _youtube_runtime_opts(self) -> dict:
        return {
            "js_runtimes": {
                "node": {"path": "/usr/bin/node"},
            },
            "remote_components": ["ejs:github"],
        }

    def _ensure_not_canceled(self, should_cancel: Callable[[], bool] | None) -> None:
        if should_cancel and should_cancel():
            raise JobCanceled("Job canceled by user")

    def _extract_playlist_entries(
        self, url: str, cookies_path: str | None
    ) -> tuple[str, list[dict]]:
        probe_opts = {"quiet": True, "no_warnings": True, **self._youtube_runtime_opts()}
        if cookies_path:
            probe_opts["cookiefile"] = cookies_path

        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)

        title = info.get("title") or "playlist"
        entries = [e for e in (info.get("entries") or []) if e]
        return title, entries

    def _make_prefix(self, idx: int, total: int) -> str:
        width = max(2, len(str(total)))
        return f"{idx:0{width}d}-"

    def _download_audio(
        self,
        url: str,
        out_dir: Path,
        is_playlist: bool,
        split_title: bool,
        cookies_path: str | None,
        progress_cb: (
            Callable[[Optional[int], str, Optional[int], Optional[int]], None] | None
        ) = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ProcessResult:
        self._ensure_not_canceled(should_cancel)
        # We keep the output template identical for single vs playlist;
        # yt-dlp decides naming per-item.
        outtmpl = str(out_dir / "%(title).200s.%(ext)s")
        noplaylist = not is_playlist

        hook = self._build_progress_hook(
            progress_cb, is_playlist=is_playlist, should_cancel=should_cancel
        )
        opts = self._common_opts(
            outtmpl=outtmpl,
            noplaylist=noplaylist,
            cookies_path=cookies_path,
            progress_hook=hook,
        )
        opts["parse_metadata"] = self._parse_metadata_rules(split_title)

        # Best audio + convert to mp3 via FFmpeg.
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "0",
                    },
                    # IMPORTANT: metadata first, then embed thumbnail (when enabled).
                    *self._metadata_postprocessors(),
                ],
            }
        )

        if progress_cb:
            progress_cb(0, "starting", None, None)

        with yt_dlp.YoutubeDL(opts) as ydl:
            self._ensure_not_canceled(should_cancel)
            ydl.download([url])

        if progress_cb:
            progress_cb(95, "postprocessing", None, None)

        if is_playlist:
            # Delegate zipping to the packager module.
            zip_path = out_dir / "result.zip"
            sel = self._packager.zip_outputs(
                out_dir=out_dir, zip_path=zip_path, allowed_ext={".mp3"}
            )

            if progress_cb:
                progress_cb(100, "done", 0, 0)

            return ProcessResult(
                output_path=sel.path, output_type=sel.output_type, is_playlist=True
            )

        # Single-file output: pick the first produced MP3.
        sel = self._packager.pick_first(out_dir, exts={".mp3"})

        if progress_cb:
            progress_cb(100, "done", 0, 0)

        return ProcessResult(output_path=sel.path, output_type="mp3", is_playlist=False)

    def _download_video(
        self,
        url: str,
        out_dir: Path,
        is_playlist: bool,
        height: Optional[int],
        split_title: bool,
        cookies_path: str | None,
        progress_cb: (
            Callable[[Optional[int], str, Optional[int], Optional[int]], None] | None
        ) = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ProcessResult:
        self._ensure_not_canceled(should_cancel)
        outtmpl = str(out_dir / "%(title).200s.%(ext)s")
        noplaylist = not is_playlist

        # yt-dlp canonical selection: bv*+ba/b; we constrain height if requested.
        if height:
            fmt = f"bv*[height<={height}]+ba/b[height<={height}]"
        else:
            fmt = "bv*+ba/b"

        hook = self._build_progress_hook(
            progress_cb, is_playlist=is_playlist, should_cancel=should_cancel
        )
        opts = self._common_opts(
            outtmpl=outtmpl,
            noplaylist=noplaylist,
            cookies_path=cookies_path,
            progress_hook=hook,
        )
        opts["parse_metadata"] = self._parse_metadata_rules(split_title)

        opts.update(
            {
                "format": fmt,
                "merge_output_format": "mp4",
                "postprocessors": [
                    *self._metadata_postprocessors(),
                ],
            }
        )

        if progress_cb:
            progress_cb(0, "starting", None, None)

        with yt_dlp.YoutubeDL(opts) as ydl:
            self._ensure_not_canceled(should_cancel)
            ydl.download([url])

        if progress_cb:
            progress_cb(95, "postprocessing", None, None)

        if is_playlist:
            # Delegate zipping to the packager module.
            zip_path = out_dir / "result.zip"
            sel = self._packager.zip_outputs(
                out_dir=out_dir,
                zip_path=zip_path,
                allowed_ext={".mp4", ".mkv", ".webm"},
            )

            if progress_cb:
                progress_cb(100, "done", 0, 0)

            return ProcessResult(
                output_path=sel.path, output_type=sel.output_type, is_playlist=True
            )

        # Single-file output: pick the first produced video file.
        sel = self._packager.pick_first(out_dir, exts={".mp4", ".mkv", ".webm"})

        if progress_cb:
            progress_cb(100, "done", 0, 0)

        return ProcessResult(
            output_path=sel.path, output_type=sel.output_type, is_playlist=False
        )

    def _metadata_postprocessors(self) -> list[dict]:
        pps: list[dict] = []

        if settings.embed_metadata:
            # Adds/embeds metadata into the final media container.
            pps.append({"key": "FFmpegMetadata", "add_metadata": True})

        if settings.embed_thumbnail:
            # Embed thumbnail as cover art.
            pps.append({"key": "EmbedThumbnail"})

        return pps

    def _should_split_title(self, info: dict, url: str, is_playlist: bool) -> bool:
        # Conservative: never split titles inside playlists (avoid mixed-content issues).
        if is_playlist:
            return False

        # If extractor already provided structured music metadata, do not override it.
        if (
            info.get("artist")
            or info.get("album")
            or info.get("track")
            or info.get("album_artist")
        ):
            return False
        if info.get("artists"):
            return False

        # YouTube Music URLs are more likely to have reliable artist/track metadata.
        if "music.youtube.com" in url.lower():
            return False

        title = (info.get("title") or "").strip()
        # Only split when it really looks like "Artist - Title".
        return " - " in title and len(title) >= 5

    def _parse_metadata_rules(self, split_title: bool) -> list[str]:
        rules: list[str] = []

        # Apply only when we decided it's safe; avoids overriding real metadata.
        if split_title:
            rules.append("title:%(artist)s - %(title)s")

        # Playlist mapping (safe even for single; fields just won't exist).
        rules += [
            "playlist_title:%(album)s",
            "playlist_index:%(track_number)s",
            "uploader:%(album_artist)s",
        ]
        return rules

    def _build_progress_hook(
        self,
        progress_cb,
        is_playlist: bool,
        should_cancel: Callable[[], bool] | None = None,
    ):
        def hook(d: dict):
            self._ensure_not_canceled(should_cancel)
            if not progress_cb:
                return

            status = d.get("status")
            if status == "finished":
                stage = "finalizing"
                eta_seconds = 0
                speed_bps = 0
            else:
                stage = "downloading"

            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes")

            eta = d.get("eta")
            speed = d.get("speed")  # bytes/sec

            eta_seconds = int(eta) if isinstance(eta, (int, float)) else None
            speed_bps = int(speed) if isinstance(speed, (int, float)) else None

            percent = None
            if (
                isinstance(total, (int, float))
                and isinstance(downloaded, (int, float))
                and total > 0
            ):
                item_pct = int(min(99, (downloaded / total) * 100))

                if is_playlist:
                    info = d.get("info_dict") or {}
                    idx = info.get("playlist_index")
                    n = info.get("n_entries") or info.get("playlist_count")
                    if isinstance(idx, int) and isinstance(n, int) and n > 0:
                        overall = ((idx - 1) + (item_pct / 100.0)) / n * 100.0
                        percent = int(min(99, overall))
                        stage = f"downloading item {idx}/{n}"
                    else:
                        percent = item_pct
                else:
                    percent = item_pct

            progress_cb(percent, stage, eta_seconds, speed_bps)

        return hook

    def _build_item_progress_hook(
        self,
        progress_cb,
        idx: int,
        total: int,
        should_cancel: Callable[[], bool] | None = None,
    ):
        def hook(d: dict):
            self._ensure_not_canceled(should_cancel)
            if not progress_cb:
                return

            status = d.get("status")
            eta = d.get("eta")
            speed = d.get("speed")

            eta_seconds = int(eta) if isinstance(eta, (int, float)) else None
            speed_bps = int(speed) if isinstance(speed, (int, float)) else None

            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes")

            pct = None
            if (
                isinstance(total_bytes, (int, float))
                and isinstance(downloaded, (int, float))
                and total_bytes > 0
            ):
                item_pct = min(99, int((downloaded / total_bytes) * 100))
                overall = ((idx - 1) + (item_pct / 100.0)) / max(1, total) * 100.0
                pct = min(99, int(overall))

            stage = "downloading"
            if status == "downloading":
                stage = f"downloading item {idx}/{total}"
            elif status == "finished":
                stage = f"finalizing item {idx}/{total}"

            progress_cb(pct, stage, eta_seconds, speed_bps)

        return hook

    def _download_one_audio(
        self,
        item_url: str,
        out_dir: Path,
        prefix: str,
        quality: str,
        cookies_path: str | None,
        progress_cb=None,
        idx: int = 1,
        total: int = 1,
        should_cancel: Callable[[], bool] | None = None,
    ):
        self._ensure_not_canceled(should_cancel)
        outtmpl = str(out_dir / f"{prefix}%(title).200s.%(ext)s")
        hook = self._build_item_progress_hook(
            progress_cb, idx, total, should_cancel=should_cancel
        )
        opts = self._common_opts(
            outtmpl=outtmpl,
            noplaylist=True,
            cookies_path=cookies_path,
            progress_hook=hook,
        )

        opts["parse_metadata"] = self._parse_metadata_rules(
            split_title=False
        )  # keep conservative in playlists
        opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "0",
                    },
                    *self._metadata_postprocessors(),
                ],
            }
        )

        with yt_dlp.YoutubeDL(opts) as ydl:
            self._ensure_not_canceled(should_cancel)
            ydl.download([item_url])

        # pick the produced mp3 for this prefix
        candidates = sorted(out_dir.glob(f"{prefix}*.mp3"))
        if candidates:
            return candidates[0]

        # fallback (rare)
        return self._packager.pick_first(out_dir, exts={".mp3"}).path

    def _download_one_video(
        self,
        item_url: str,
        out_dir: Path,
        prefix: str,
        height: Optional[int],
        cookies_path: str | None,
        progress_cb=None,
        idx: int = 1,
        total: int = 1,
        should_cancel: Callable[[], bool] | None = None,
    ):
        self._ensure_not_canceled(should_cancel)
        outtmpl = str(out_dir / f"{prefix}%(title).200s.%(ext)s")
        hook = self._build_item_progress_hook(
            progress_cb, idx, total, should_cancel=should_cancel
        )
        opts = self._common_opts(
            outtmpl=outtmpl,
            noplaylist=True,
            cookies_path=cookies_path,
            progress_hook=hook,
        )

        if height:
            fmt = f"bv*[height<={height}]+ba/b[height<={height}]"
        else:
            fmt = "bv*+ba/b"

        opts["parse_metadata"] = self._parse_metadata_rules(split_title=False)
        opts.update(
            {
                "format": fmt,
                "merge_output_format": "mp4",
                "postprocessors": [*self._metadata_postprocessors()],
            }
        )

        with yt_dlp.YoutubeDL(opts) as ydl:
            self._ensure_not_canceled(should_cancel)
            ydl.download([item_url])

        # prefer mp4
        mp4 = sorted(out_dir.glob(f"{prefix}*.mp4"))
        if mp4:
            return mp4[0]

        # fallback containers
        for ext in ("mkv", "webm"):
            c = sorted(out_dir.glob(f"{prefix}*.{ext}"))
            if c:
                return c[0]

        return self._packager.pick_first(out_dir, exts={".mp4", ".mkv", ".webm"}).path

    def _process_playlist(
        self,
        job_id: str,
        playlist_url: str,
        mode: str,
        quality: str,
        height: Optional[int],
        out_dir: Path,
        cookies_path: str | None,
        progress_cb=None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ProcessResult:
        self._ensure_not_canceled(should_cancel)

        playlist_title, entries = self._extract_playlist_entries(
            playlist_url, cookies_path
        )
        total = len(entries)

        success_files: list[Path] = []
        failures: list[PlaylistFailure] = []

        if progress_cb:
            progress_cb(0, "extracting playlist", None, None)

        for i, e in enumerate(entries, start=1):
            self._ensure_not_canceled(should_cancel)
            prefix = self._make_prefix(i, total)
            video_id = e.get("id") or e.get("url")
            title = e.get("title")
            item_url = e.get("webpage_url") or (
                f"https://www.youtube.com/watch?v={video_id}" if video_id else None
            )

            if not item_url:
                failures.append(
                    PlaylistFailure(
                        index=i,
                        title=title,
                        video_id=video_id,
                        url=None,
                        reason_code="UNAVAILABLE",
                        error_message="Missing item URL in playlist entries",
                    )
                )
                continue

            try:
                if progress_cb:
                    base_pct = int(((i - 1) / max(1, total)) * 100)
                    progress_cb(base_pct, f"starting item {i}/{total}", None, None)

                if mode == "audio":
                    p = self._download_one_audio(
                        item_url=item_url,
                        out_dir=out_dir,
                        prefix=prefix,
                        quality=quality,
                        cookies_path=cookies_path,
                        progress_cb=progress_cb,
                        idx=i,
                        total=total,
                        should_cancel=should_cancel,
                    )
                    success_files.append(p)
                else:
                    p = self._download_one_video(
                        item_url=item_url,
                        out_dir=out_dir,
                        prefix=prefix,
                        height=height,
                        cookies_path=cookies_path,
                        progress_cb=progress_cb,
                        idx=i,
                        total=total,
                        should_cancel=should_cancel,
                    )
                    success_files.append(p)

            except Exception as ex:
                if isinstance(ex, JobCanceled):
                    raise
                failures.append(
                    PlaylistFailure(
                        index=i,
                        title=title,
                        video_id=video_id,
                        url=item_url,
                        reason_code=classify_error(ex),
                        error_message=str(ex),
                    )
                )
                # continue to next item
                continue

        # Write report.json always
        report = PlaylistReport(
            job_id=job_id,
            source_url=playlist_url,
            mode=mode,
            quality=quality,
            total_items=total,
            succeeded=len(success_files),
            failed=len(failures),
            success_files=[p.name for p in success_files],
            failures=failures,
        )
        report_path = self._reporter.write_playlist_report(out_dir, report)

        if progress_cb:
            progress_cb(95, "packaging", None, None)

        # Some succeeded -> return ZIP with report included
        if success_files:
            zip_path = out_dir / "result.zip"
            self._packager.zip_files(zip_path, success_files + [report_path])
            # return with playlist stats
            return ProcessResult(
                output_path=zip_path,
                output_type="zip",
                is_playlist=True,
                playlist_total=total,
                playlist_succeeded=len(success_files),
                playlist_failed=len(failures),
            )

        # All failed
        raise AllPlaylistItemsFailed(
            "All playlist items failed. See report.json for details.",
            total=total,
            failed=len(failures),
        )
