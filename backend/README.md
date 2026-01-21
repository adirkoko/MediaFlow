# MediaFlow Backend

A small, clear, and practical **FastAPI** backend for downloading and processing YouTube content (single videos or playlists), with a focus on **readability**, **stability**, and **simple operational control**.

This repository is intentionally **not** an enterprise platform. It is a lightweight tool designed for a controlled set of authorized users.

---

## Features

- **Authenticated access** (username/password → JWT Bearer token).
- **Jobs API** for single videos or playlists:
  - Audio or video output
  - Quality selection (e.g., `best`, `720p`, `1080p`)
- **MP3 output** for audio (via FFmpeg).
- **Metadata embedding** (tags + cover art) for audio/video (where supported by container/player).
- **Playlist support**:
  - Processes items sequentially
  - Returns a `.zip` archive for convenience
- **Load control**:
  - Global concurrency limit
  - Per-user active jobs quota
  - Request **deduplication** (reuse in-flight jobs for identical requests)
- **Progress tracking**:
  - `progress_percent`, `stage`, `eta_seconds`, `speed_bps`
  - Live updates via **SSE** (`/jobs/{job_id}/events`)
- **Usage tracking** (`/me/usage`): basic counters and average processing time
- **Output TTL cleanup**: automatically removes old job output folders

---

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLite (jobs + usage events)
- yt-dlp (download/extract)
- FFmpeg (merge/convert/embed)

---

## Project Layout

```
backend/
  app/
    main.py
    api/
      routes_auth.py
      routes_health.py
      routes_jobs.py
      routes_usage.py
    core/
      config.py
      deps.py
      errors.py
      exceptions.py
      logging.py
      security.py
    infrastructure/
      db.py
      jobs_store.py
      users_store.py
      usage_store.py
    services/
      backoff.py
      cleanup.py
      cookies.py
      job_manager.py
      worker.py
      youtube_processor.py
    models/
      schemas.py
  data/
    users.json
    app.sqlite
  outputs/
  README.md
  LICENSE
  .gitignore
  .env.example
  requirements.txt
```

---

## Requirements

### 1) Python
Install **Python 3.11+** and ensure `python` is on your PATH.

### 2) FFmpeg

#### Windows
Place `ffmpeg.exe` in:

```
backend/bin/ffmpeg.exe
```

Make sure the file exists and is executable.

#### Linux (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install ffmpeg
```

### 3) Git
Install Git to clone/push to GitHub.

---

## Quickstart (Development)

From the repository root:

### 1) Create and activate a virtual environment
#### Windows (CMD)
```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
```

#### Linux/macOS
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3) Create `.env`
Copy `.env.example` → `.env` and set values as needed:

```env
JWT_SECRET=CHANGE_ME_TO_A_LONG_RANDOM_VALUE
```

> Do not commit `.env`.

### 4) Create the first user

1) Generate a password hash:
```bash
python -c "from app.core.security import hash_password; print(hash_password('ChangeMe123!'))"
```

2) Put the result in `data/users.json`:
```json
{
  "users": [
    {
      "username": "admin",
      "password_hash": "PASTE_HASH_HERE"
    }
  ]
}
```

### 5) Run the server
```bash
uvicorn app.main:app --reload
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

---

## Configuration

The application reads configuration from environment variables (see `app/core/config.py`).

Common settings:

| Variable | Default | Description |
|---|---:|---|
| `APP_NAME` | `MediaFlow Backend` | Service name |
| `ENV` | `dev` | Environment label |
| `JWT_SECRET` | `CHANGE_ME` | JWT signing secret (must override) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXP_MINUTES` | `60` | Token lifetime |
| `USERS_FILE` | `data/users.json` | Users store path |
| `DB_PATH` | `data/app.sqlite` | SQLite DB path |
| `OUTPUTS_DIR` | `outputs` | Output root folder |
| `MAX_PARALLEL_JOBS` | `2` | Global concurrent processing limit |
| `QUEUE_MAX_SIZE` | `50` | In-memory queue capacity |
| `MAX_ACTIVE_JOBS_PER_USER` | `2` | Per-user quota for queued/running jobs |
| `DEDUP_WINDOW_MINUTES` | `60` | Dedup window for identical requests |
| `OUTPUTS_TTL_HOURS` | `24` | Output folder time-to-live |
| `OUTPUTS_CLEANUP_INTERVAL_MINUTES` | `60` | Cleanup scheduler interval |
| `EMBED_METADATA` | `true` | Embed tags into output |
| `EMBED_THUMBNAIL` | `true` | Embed thumbnail as cover art |
| `THUMBNAIL_CONVERT_FORMAT` | `jpg` | Convert thumbnails to this format |
| `MAX_ATTEMPTS` | `4` | Backoff attempts for transient errors |
| `BACKOFF_BASE_SECONDS` | `2.0` | Backoff base delay |
| `COOKIES_FILE` | *(empty)* | Optional absolute path to cookies.txt (see below) |

---

## Authentication

1) Login:
- `POST /auth/login` with JSON body:
```json
{"username":"admin","password":"ChangeMe123!"}
```

2) Use the returned token:
- Add header:
```
Authorization: Bearer <access_token>
```

### Swagger Authorization
In `/docs` click **Authorize** and paste:
```
Bearer <access_token>
```

---

## API Overview

### Health
- `GET /health`

### Jobs
- `POST /jobs` — create job (audio/video, quality, url)
- `GET /jobs` — list last jobs for current user (default 50)
- `GET /jobs/{job_id}` — get job status + metadata + progress
- `GET /jobs/{job_id}/download` — download output file (mp3/mp4/zip)
- `GET /jobs/{job_id}/events` — **SSE** live progress stream

### Usage
- `GET /me/usage` — basic per-user usage summary

---

## Jobs Workflow

1) Create a job:
```bash
curl -X POST "http://127.0.0.1:8000/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\",\"mode\":\"audio\",\"quality\":\"best\"}"
```

2) Poll status:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/jobs/<job_id>"
```

3) Download when `status == "succeeded"`:
```bash
curl -L -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/jobs/<job_id>/download" \
  -o output.bin
```

---

## Live Progress (SSE)

Subscribe to job events:

```bash
curl -N -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/jobs/<job_id>/events"
```

Event payload example:

```json
{
  "job_id": "...",
  "status": "running",
  "progress_percent": 42,
  "stage": "downloading item 2/10",
  "eta_seconds": 15,
  "speed_bps": 1250000,
  "updated_at": "2026-01-21T12:34:56+00:00",
  "output_filename": null,
  "output_type": null,
  "error_code": null,
  "error_message": null
}
```

Notes:
- Progress is a **best-effort** approximation (especially for playlists).
- `eta_seconds` and `speed_bps` are reported when available from the downloader; during post-processing they may be `null`/`0`.

---

## Metadata Embedding (Tags + Cover Art)

When enabled (`EMBED_METADATA=true`, `EMBED_THUMBNAIL=true`):
- Audio output (MP3) will include tags and embedded cover image (where supported by your media player).
- Video output may include metadata and embedded thumbnail depending on container and player.

For naming, output filenames are based on the YouTube title with Windows-safe sanitization.

---

## Usage Tracking

`GET /me/usage` returns a lightweight summary:

- total requests
- success/failed counts
- counts by mode (audio/video)
- counts by content type (single/playlist)
- average duration (ms)

This is intended for operational visibility, not analytics.

---

## Output Management & TTL Cleanup

Downloaded/processed files are stored under:

```
backend/outputs/<job_id>/
```

A background cleanup task periodically deletes old job folders based on:
- `OUTPUTS_TTL_HOURS`
- `OUTPUTS_CLEANUP_INTERVAL_MINUTES`

---

## Optional: Cookies for Legitimate Authenticated Access

Some content may require authentication (private/unlisted/age-gated content or personal access).

You may provide a cookies file path via `.env`:

```env
COOKIES_FILE=C:\path\to\cookies.txt
```

Security notes:
- **Do not commit cookies**.
- Treat cookies as sensitive credentials.
- Prefer storing them outside the repository.
- The backend copies cookies to a per-job temporary file and deletes it after processing.

---

## Troubleshooting

### FFmpeg not found
- Windows: ensure `backend/bin/ffmpeg.exe` exists.
- Linux: ensure `ffmpeg` is installed and on PATH.

### 401 Unauthorized
- Login again and ensure you send `Authorization: Bearer <token>`.

### 429 Too many active jobs
- You hit the per-user active job quota. Wait for queued/running jobs to finish, or increase `MAX_ACTIVE_JOBS_PER_USER`.

### Job succeeded but download fails
- Check `output_filename`/`output_type` in `GET /jobs/{job_id}`.
- Confirm the outputs directory exists and TTL cleanup hasn't removed it.

---

## Development Notes

- Logs are printed to stdout.
- SQLite DB is stored at `data/app.sqlite` by default.
- Concurrency and queue sizing are controlled via env vars.

---

## Roadmap (Optional Ideas)

- `GET /jobs/{job_id}/log` endpoint (serve job.log safely)
- Admin endpoints for manual user management
- Optional frontend UI
- Better playlist progress estimation
- Optional storage backends (S3/local network path)

---

## Legal Disclaimer

**This project is provided for educational and research purposes only.**

By accessing, downloading, or using this software, you explicitly agree to the following terms:

1.  **Compliance:** You are solely responsible for ensuring that your use of this software complies with all applicable local, state, and federal laws, as well as the Terms of Service of any third-party platforms (including but not limited to YouTube, YouTube Music, and Google).
2.  **No Liability:** The developer ("adirkoko") assumes **no liability** for any misuse of this software, including but not limited to copyright infringement, account suspensions, or legal actions taken against the user.
3.  **"As Is" Basis:** This software is provided "as is", without warranty of any kind, express or implied. The entire risk as to the quality and performance of the software is with you.

**Use this tool responsibly and respect the rights of content creators.**

## 🎖 Acknowledgements & Third-Party Licenses

This project leverages powerful open-source tools. We gratefully acknowledge their contributions:

* **[yt-dlp](https://github.com/yt-dlp/yt-dlp):** A feature-rich command-line audio/video downloader (Unlicense/Public Domain).
* **[FFmpeg](https://ffmpeg.org/):** A complete, cross-platform solution to record, convert and stream audio and video (LGPL v2.1+).
* **[FastAPI](https://fastapi.tiangolo.com/):** A modern, fast web framework for building APIs with Python (MIT License).

*The names and logos of third-party services are property of their respective owners.*