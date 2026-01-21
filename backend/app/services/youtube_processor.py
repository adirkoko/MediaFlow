from __future__ import annotations
import zipfile
import yt_dlp
from app.core.config import settings
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass
from pathlib import Path
from typing import Optional



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
    def process(
        self,
        job_id: str,
        url: str,
        mode: str,
        quality: str,
        cookies_path: str | None = None,
        progress_cb: Callable[[Optional[int], str], None] | None = None,
    ) -> ProcessResult:
        out_dir = Path(settings.outputs_dir) / job_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # Detect playlist vs single (so we can decide zip vs single fixed output name)
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(url, download=False)

        is_playlist = bool(
            info and (info.get("_type") == "playlist" or info.get("entries"))
        )
        split_title = self._should_split_title(info or {}, url, is_playlist)
        height = _parse_quality_to_height(quality)

        if mode == "audio":
            return self._download_audio(
                url=url,
                out_dir=out_dir,
                is_playlist=is_playlist,
                split_title=split_title,
                cookies_path=cookies_path,
                progress_cb=progress_cb,
            )
        if mode == "video":
            return self._download_video(
                url=url,
                out_dir=out_dir,
                is_playlist=is_playlist,
                height=height,
                split_title=split_title,
                cookies_path=cookies_path,
                progress_cb=progress_cb,
            )

        raise ValueError(f"Unsupported mode: {mode}")

    def _common_opts(
        self, outtmpl: str, noplaylist: bool, cookies_path: str | None, progress_hook=None) -> dict:
        ffmpeg_bin = Path.cwd() / "bin" / "ffmpeg.exe"

        opts = {
            "outtmpl": outtmpl,
            "noplaylist": noplaylist,
            "windowsfilenames": True,
            "restrictfilenames": False,
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
            "ffmpeg_location": str(ffmpeg_bin),
        }

        if cookies_path:
            opts["cookiefile"] = cookies_path

        if settings.embed_thumbnail:
            opts["writethumbnail"] = True
            opts["convertthumbnails"] = settings.thumbnail_convert_format

        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        return opts

    def _download_audio(
        self,
        url: str,
        out_dir: Path,
        is_playlist: bool,
        split_title: bool,
        cookies_path: str | None,
        progress_cb: Callable[[Optional[int], str], None] | None = None,
    ) -> ProcessResult:
        if is_playlist:
            outtmpl = str(out_dir / "%(title).200s.%(ext)s")
            noplaylist = False
        else:
            outtmpl = str(out_dir / "%(title).200s.%(ext)s")
            noplaylist = True

        hook = self._build_progress_hook(progress_cb, is_playlist=is_playlist)
        opts = self._common_opts(outtmpl=outtmpl, noplaylist=noplaylist, cookies_path=cookies_path, progress_hook=hook)
        opts["parse_metadata"] = self._parse_metadata_rules(split_title)

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

        if progress_cb:
            progress_cb(0, "starting")

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if progress_cb:
            progress_cb(95, "postprocessing")

        if is_playlist:
            zip_path = out_dir / "result.zip"
            self._zip_outputs(out_dir=out_dir, zip_path=zip_path, allowed_ext={".mp3"})
        
            if progress_cb:
                progress_cb(100, "done")

            return ProcessResult(output_path=zip_path, output_type="zip", is_playlist=True)

        fallback = self._pick_first(out_dir, exts={".mp3"})
        if progress_cb:
            progress_cb(100, "done")
        return ProcessResult(output_path=fallback, output_type="mp3", is_playlist=False)

    def _download_video(
        self,
        url: str,
        out_dir: Path,
        is_playlist: bool,
        height: Optional[int],
        split_title: bool,
        cookies_path: str | None,
        progress_cb: Callable[[Optional[int], str], None] | None = None,
    ) -> ProcessResult:
        if is_playlist:
            outtmpl = str(out_dir / "%(title).200s.%(ext)s")
            noplaylist = False
        else:
            outtmpl = str(out_dir / "%(title).200s.%(ext)s")
            noplaylist = True

        # yt-dlp format selection examples: bv*+ba/b is canonical :contentReference[oaicite:3]{index=3}
        if height:
            fmt = f"bv*[height<={height}]+ba/b[height<={height}]"
        else:
            fmt = "bv*+ba/b"

        hook = self._build_progress_hook(progress_cb, is_playlist=is_playlist)
        opts = self._common_opts(outtmpl=outtmpl, noplaylist=noplaylist, cookies_path=cookies_path, progress_hook=hook)

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
            progress_cb(0, "starting")

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if progress_cb:
            progress_cb(95, "postprocessing")

        if is_playlist:
            zip_path = out_dir / "result.zip"
            self._zip_outputs(
                out_dir=out_dir,
                zip_path=zip_path,
                allowed_ext={".mp4", ".mkv", ".webm"},
            )

            if progress_cb:
                progress_cb(100, "done")

            return ProcessResult(output_path=zip_path, output_type="zip", is_playlist=True)

        fallback = self._pick_first(out_dir, exts={".mp4", ".mkv", ".webm"})
        if progress_cb:
            progress_cb(100, "done")

        return ProcessResult(
            output_path=fallback,
            output_type=fallback.suffix.lower().lstrip("."),
            is_playlist=False,
        )

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

    def _should_split_title(self, info: dict, url: str, is_playlist: bool) -> bool:
        # Conservative: don't split titles inside playlists (avoid breaking mixed content)
        if is_playlist:
            return False

        # If extractor already provided structured music metadata, do NOT override it
        if (
            info.get("artist")
            or info.get("album")
            or info.get("track")
            or info.get("album_artist")
        ):
            return False
        if info.get("artists"):  # sometimes list of artists exists
            return False

        # YouTube Music URLs are more likely to have real artist/track data
        if "music.youtube.com" in url.lower():
            return False

        title = (info.get("title") or "").strip()
        # Only split when it really looks like "Artist - Title"
        return " - " in title and len(title) >= 5

    def _parse_metadata_rules(self, split_title: bool) -> list[str]:
        rules: list[str] = []

        # Only apply this if we decided it's safe. This avoids overriding existing artist.
        if split_title:
            rules.append(
                "title:%(artist)s - %(title)s"
            )  # official example :contentReference[oaicite:1]{index=1}

        # Playlist mapping (safe even for single; fields just won't exist)
        rules += [
            "playlist_title:%(album)s",
            "playlist_index:%(track_number)s",
            "uploader:%(album_artist)s",
        ]
        return rules

    def _build_progress_hook(self, progress_cb, is_playlist: bool):
        def hook(d: dict):
            if not progress_cb:
                return

            status = d.get("status")
            stage = "downloading" if status == "downloading" else "finalizing" if status == "finished" else "working"

            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes")

            percent = None
            if isinstance(total, (int, float)) and isinstance(downloaded, (int, float)) and total > 0:
                item_pct = int(min(99, (downloaded / total) * 100))

                # Playlist-aware progress (best-effort)
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

            progress_cb(percent, stage)
        return hook
