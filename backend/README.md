# MediaFlow Backend

A small, clear, and practical **FastAPI** backend for downloading and processing YouTube content (single videos or playlists), with a focus on **readability**, **stability**, and **simple operational control**.

This repository is intentionally **not** an enterprise platform. It is a lightweight tool designed for a controlled set of authorized users.

## Where To Start

- **Production (Ubuntu + Docker Compose):** see repository root [README.md](../README.md) and [DEPLOY.md](../DEPLOY.md).
- **This file (`backend/README.md`):** backend-focused docs and local development flow.

---

## Features

- **Authenticated access** (username/password -> JWT Bearer token).
- **Admin user management API** for DB-backed users (create/update/disable/enable/soft-delete/reset password/revoke tokens).
- **Jobs API** for single videos or playlists:
  - Preview endpoint before job creation (title, thumbnail, playlist/video basics, available video qualities when yt-dlp can resolve them)
  - Audio or video output
  - Video quality selection (`best`, `144p`, `240p`, `360p`, `480p`, `720p`, `1080p`, `1440p`, `2160p`)
  - Audio always uses best available audio and therefore accepts only `quality=best`
  - Live progress includes ETA and speed (eta_seconds, speed_bps)
- **MP3 output** for audio (via FFmpeg).
- **Metadata embedding** (tags + cover art) for audio/video (where supported by container/player).
- **YouTube URL allowlist**: job URLs must be YouTube / YouTube Music / youtu.be URLs.
- **Playlist support**:
  - Processes item-by-item (continues even if some items fail)
  - Counts an item as successful only when an output file for that specific item was produced
  - Produces `result.zip` with all successfully downloaded items
  - Generates `report.json` with per-item failures and reasons
  - Playlist summary fields: `playlist_total`, `playlist_succeeded`, `playlist_failed` (available via job status APIs)
  - Job is succeeded if at least one item succeeds, otherwise failed with a clear error
- **Load control**:
  - Global concurrency limit
  - Per-user active jobs quota
  - Request **deduplication** (reuse in-flight jobs for identical requests)
- **Progress tracking**:
  - `progress_percent`, `stage`, `eta_seconds`, `speed_bps`
  - Live updates via **SSE** (`/jobs/{job_id}/events`)
- **Usage tracking** (`/me/usage`): basic counters and average processing time
- **Admin audit log basics** for user-management actions.
- **Output TTL cleanup**: automatically removes old job output folders

---

## Tech Stack

- Python 3.11+
- FastAPI + Uvicorn
- SQLite (users, jobs, and usage events)
- yt-dlp (download/extract)
- FFmpeg (merge/convert/embed)
- Node.js (used by yt-dlp for YouTube JavaScript challenge solving)

---

## Project Layout

```
backend/
  app/
    main.py
    api/
      routes_admin_quotas.py
      routes_admin_jobs.py
      routes_admin_security.py
      routes_admin_users.py
      routes_admin_usage.py
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
      users.py
    infrastructure/
      audit_logs_repository.py
      db.py
      jobs_store.py
      quotas_repository.py
      security_repository.py
      usage_repository.py
      users_repository.py
      usage_store.py
    services/
      admin_users_service.py
      backoff.py
      cleanup.py
      cookies.py
      error_codes.py
      job_logging.py
      job_manager.py
      media_preview.py
      packaging.py
      quota_service.py
      rate_limiter.py
      reporting.py
      usage_service.py
      worker.py
      youtube_processor.py
    models/
      schemas.py
  scripts/
    migrate_users_json_to_db.py
  data/
    app.sqlite
  outputs/
  README.md
  LICENSE
  .gitignore
  .env.example
  requirements.txt
```

> In production, `data` and `outputs` can be external host paths by setting `USERS_FILE`, `DB_PATH`, and `OUTPUTS_DIR` (as configured by root-level compose/env files).

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

#### Docker
The backend Docker image installs FFmpeg automatically. In Docker/Linux, `ffmpeg` and `ffprobe` are expected to be available on `PATH`.

### 3) Node.js

Node.js is used by yt-dlp to solve YouTube JavaScript challenges required by some media formats.

#### Windows
Install Node.js and ensure `node` is available on your PATH.

#### Linux (Debian/Ubuntu)
```bash
sudo apt update
sudo apt install nodejs
```

#### Docker

The backend Docker image installs Node.js automatically.

### 4) Git
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
Copy `.env.example` -> `.env` and set values as needed:

```env
JWT_SECRET=CHANGE_ME_TO_A_LONG_RANDOM_VALUE
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

> Do not commit `.env`.

### 4) Create the first user

1) Generate a password hash:
```bash
python -c "from app.core.security import hash_password; print(hash_password('ChangeMe123!'))"
```

2) Put the result in a temporary legacy `data/users.json` migration file:
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

3) Migrate the user into SQLite:
```bash
python scripts/migrate_users_json_to_db.py
```

After migration, `data/users.json` is no longer used as the runtime authentication source.

### 5) Run the server
```bash
uvicorn app.main:app --reload
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

## Production Deployment

For Ubuntu Server deployment using one compose stack (backend + frontend + persistent external data), use:
- `../docker-compose.yml`
- `../.env.production.example`
- `../DEPLOY.md`

On startup, the backend performs **startup reconciliation**:
- Any stale `queued` / `running` jobs from a previous process are automatically moved to `failed`.
- Those jobs receive `error_code=SERVER_RESTART` and an explanatory error message.

---

## Configuration

The application reads configuration from environment variables (see `app/core/config.py`).

Common settings:

| Variable | Default | Description |
|---|---:|---|
| `APP_NAME` | `MediaFlow Backend` | Service name |
| `ENV` | `dev` | Environment label |
| `JWT_SECRET` | `CHANGE_ME` | JWT signing secret (must override) |
| `CORS_ORIGINS` | *(required)* | Comma-separated allowed origins (e.g., `http://localhost:3000`) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `JWT_EXP_MINUTES` | `60` | Token lifetime |
| `USERS_FILE` | `data/users.json` | Legacy users JSON path used by the migration script |
| `DB_PATH` | `data/app.sqlite` | SQLite DB path |
| `OUTPUTS_DIR` | `outputs` | Output root folder |
| `MAX_PARALLEL_JOBS` | `2` | Global concurrent processing limit |
| `QUEUE_MAX_SIZE` | `50` | In-memory queue capacity |
| `MAX_ACTIVE_JOBS_PER_USER` | `2` | Per-user quota for queued/running jobs |
| `DEDUP_WINDOW_MINUTES` | `60` | Dedup window for identical requests |
| `LOGIN_MAX_FAILED_PER_USERNAME` | `5` | Failed login limit per username within `LOGIN_WINDOW_MINUTES` |
| `LOGIN_MAX_FAILED_PER_IP` | `20` | Failed login limit per IP hash within `LOGIN_WINDOW_MINUTES` |
| `LOGIN_WINDOW_MINUTES` | `10` | Login brute-force counting window |
| `LOGIN_BLOCK_MINUTES` | `15` | Suggested retry delay returned for blocked logins |
| `JOB_CREATE_RATE_LIMIT_PER_MINUTE` | `20` | Per-user in-memory rate limit for `POST /jobs` |
| `JOB_PREVIEW_RATE_LIMIT_PER_MINUTE` | `30` | Per-user in-memory rate limit for `POST /jobs/preview` |
| `OUTPUTS_TTL_HOURS` | `24` | Output folder time-to-live (hours) |
| `OUTPUTS_TTL_MINUTES` | `0` | Minutes override for TTL. Use `0` to disable minutes and fall back to `OUTPUTS_TTL_HOURS`. |
| `OUTPUTS_CLEANUP_INTERVAL_MINUTES` | `60` | Cleanup scheduler interval |
| `EMBED_METADATA` | `true` | Embed tags (artist, title, album) into output |
| `EMBED_THUMBNAIL` | `true` | Embed thumbnail as cover art |
| `THUMBNAIL_CONVERT_FORMAT` | `jpg` | Convert thumbnails to this format |
| `MAX_ATTEMPTS` | `4` | Retries for transient errors (backoff) |
| `BACKOFF_BASE_SECONDS` | `2.0` | Backoff base delay |
| `YTDLP_RETRIES` | `0` | yt-dlp retry attempts (network/HTTP) |
| `YTDLP_FRAGMENT_RETRIES` | `0` | yt-dlp retry attempts for fragments |
| `YTDLP_EXTRACTOR_RETRIES` | `0` | yt-dlp retry attempts for extractor |
| `NODE_PATH` | *(empty)* | Optional explicit path to the `node` executable. Docker sets this to `/usr/bin/node`; leave empty locally to use `node` from `PATH`. |
| `YTDLP_REMOTE_COMPONENTS` | *(empty)* | Optional comma-separated yt-dlp remote components. Use `ejs:github` when YouTube requires the newer challenge solver; `true` is accepted as an alias for `ejs:github`. |
| `COOKIES_FILE` | *(empty)* | Optional absolute path to cookies.txt (see below) |

---

## Authentication

Users are stored in the SQLite `users` table. Legacy `users.json` files are only
used as migration input and are not the runtime source of truth after migration.

User records include `role`, `status`, `token_version`, `last_login_at`, and
soft-delete fields. Login is allowed only for users with `status="active"` and
`deleted_at=null`.

New JWTs use the database user id as `sub` and also include `username`, `role`,
and `token_version`. The current-user dependency checks the token version against
the database, so incrementing `token_version` invalidates older tokens. Soft
delete sets `status="deleted"` and `deleted_at`.

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

### Migrating Legacy `users.json`

To migrate existing bcrypt hashes from the old JSON store:

```bash
python scripts/migrate_users_json_to_db.py --users-file data/users.json
```

The script inserts users that do not already exist, preserves existing
`password_hash` values, sets `role="user"`, `status="active"`, and
`token_version=1`, and is safe to run more than once.

### Creating or Promoting the First Admin

The migration script imports legacy users with `role="user"`. To bootstrap admin
access, promote one trusted user directly in SQLite after migration:

```bash
sqlite3 data/app.sqlite "UPDATE users SET role='admin', updated_at=datetime('now') WHERE username='admin';"
```

For Docker production, run the same update against the mounted DB path, for
example `/srv/data/mediaflow/backend-data/app.sqlite`.

### Admin User API

Admin endpoints require a valid JWT for a user with `role="admin"`:

- `GET /admin/users` -- list users, with optional `status`, `role`, `search`, and `include_deleted` filters.
- `POST /admin/users` -- create a user. Passwords are hashed; password hashes are never returned.
- `GET /admin/users/{user_id}` -- fetch one user.
- `PATCH /admin/users/{user_id}` -- update `username`, `email`, `role`, or `status`.
- `POST /admin/users/{user_id}/disable` -- set `status="disabled"` and increment `token_version`.
- `POST /admin/users/{user_id}/enable` -- set `status="active"` and increment `token_version`; soft-deleted users cannot be re-enabled.
- `POST /admin/users/{user_id}/soft-delete` -- set `status="deleted"`, set `deleted_at`, and increment `token_version`.
- `POST /admin/users/{user_id}/reset-password` -- hash a new password and increment `token_version`.
- `POST /admin/users/{user_id}/revoke-tokens` -- increment `token_version` to invalidate issued access tokens.

Safety checks prevent an admin from disabling or soft-deleting themselves, and
prevent removing the only active admin role from your own account.

Admin actions write basic rows to `audit_logs` with action, actor, target, JSON
metadata, and timestamp. Passwords and password hashes are not written to audit
metadata.

### Quotas, Credits, and Anti-Abuse

MediaFlow stores role defaults in `role_quotas` and optional per-user overrides
in `user_quotas`. If a user override field is `null`, the role quota applies.
Default role quotas are seeded for `user` and `admin` at startup.

Job requests are estimated in credits before a job is created:

- Audio single video: `1`
- Video: `144p=1`, `240p=1`, `360p=2`, `480p=2`, `720p=3`, `1080p=5`, `1440p=8`, `2160p=12`, `best=5`
- Playlists multiply the per-item cost by the estimated item count.
- Long videos receive a simple duration multiplier when duration is known.

Quota checks run before `POST /jobs` creates a job. They enforce active jobs,
daily/weekly/monthly job counts, daily/weekly/monthly estimated credits, playlist
item limits, max video quality, and max duration when known. Rejected jobs return
`429` with a structured error and are recorded as `quota_exceeded`.

Usage is recorded in `usage_events` and rolled up into `user_usage_daily` for
today/week/month style queries. Raw URLs are not stored; usage events store a URL
hash when needed.

Login brute-force protection records `login_attempts` and temporarily blocks
excessive failures by username/IP hash. Job creation and preview endpoints also
have lightweight in-memory per-user rate limits. These rate limits are
per-process; for multi-process deployments a shared store such as Redis would be
a later upgrade.

### Admin Quota, Usage, and Security APIs

- `GET /admin/quotas/roles`
- `GET /admin/quotas/roles/{role}`
- `PATCH /admin/quotas/roles/{role}`
- `GET /admin/users/{user_id}/quota`
- `PATCH /admin/users/{user_id}/quota`
- `DELETE /admin/users/{user_id}/quota`
- `GET /admin/usage/summary?range=today|week|month`
- `GET /admin/usage/users?range=today|week|month`
- `GET /admin/usage/users/{user_id}?range=today|week|month`
- `GET /admin/usage/users/{user_id}/daily?days=30`
- `GET /admin/usage/heavy-users?range=today|week|month`
- `GET /admin/usage/quota-exceeded?range=today|week|month`
- `GET /admin/jobs`
- `GET /admin/jobs/{job_id}`
- `POST /admin/jobs/{job_id}/cancel`
- `GET /admin/security/login-attempts`
- `GET /admin/security/blocked-logins`
- `GET /admin/security/audit-logs`

Users can inspect their own limits with:

- `GET /me/usage?range=today|week|month`
- `GET /me/usage/daily?days=30`
- `GET /me/limits`

---

## API Overview

### Health
- `GET /health`

### Jobs
- `POST /jobs/preview` -- inspect a YouTube URL before creating a job
- `POST /jobs` -- create job (audio/video, quality, url)
- `POST /jobs/{job_id}/cancel` -- request cancellation (`queued` cancels immediately, `running` cancels cooperatively)
- `GET /jobs` -- list last jobs for current user (default 50)
- `GET /jobs/{job_id}` -- get job status + metadata + progress
- `GET /jobs/{job_id}/download` -- download output file (mp3/mp4/zip)
- `GET /jobs/{job_id}/report` -- download the detailed `report.json` for playlists.
- `GET /jobs/{job_id}/events` -- **SSE** live progress stream

### Usage
- `GET /me/usage` -- basic per-user usage summary
- `GET /me/usage/daily` -- per-day usage rows
- `GET /me/limits` -- effective quota, usage, and remaining limits

### Admin Users
- `GET /admin/users`
- `POST /admin/users`
- `GET /admin/users/{user_id}`
- `PATCH /admin/users/{user_id}`
- `POST /admin/users/{user_id}/disable`
- `POST /admin/users/{user_id}/enable`
- `POST /admin/users/{user_id}/soft-delete`
- `POST /admin/users/{user_id}/reset-password`
- `POST /admin/users/{user_id}/revoke-tokens`

### Admin Quotas, Usage, and Security
- `GET /admin/quotas/roles`
- `PATCH /admin/quotas/roles/{role}`
- `GET /admin/users/{user_id}/quota`
- `PATCH /admin/users/{user_id}/quota`
- `DELETE /admin/users/{user_id}/quota`
- `GET /admin/usage/summary`
- `GET /admin/usage/heavy-users`
- `GET /admin/jobs`
- `POST /admin/jobs/{job_id}/cancel`
- `GET /admin/security/login-attempts`
- `GET /admin/security/audit-logs`

---

## URL, Mode, and Quality Rules

- URLs are limited to YouTube hosts (`youtube.com`, subdomains such as `music.youtube.com`, `youtube-nocookie.com`, and `youtu.be`).
- `mode` must be either `audio` or `video`.
- `audio` supports only `quality=best`; the service always downloads the best available audio and converts it to MP3.
- `video` supports: `best`, `144p`, `240p`, `360p`, `480p`, `720p`, `1080p`, `1440p`, `2160p`.
- Numeric video values such as `720` are normalized to `720p`; unsupported values such as `banana` or `999p` are rejected.

---

## Jobs Workflow

1) Preview a URL:
```bash
curl -X POST "http://127.0.0.1:8000/jobs/preview" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\"}"
```

Response:
```json
{
  "title": "Example title",
  "thumbnail": "https://...",
  "is_playlist": false,
  "duration_seconds": 213,
  "audio_ext": "m4a",
  "audio_filesize_bytes": 3456789,
  "video_qualities": [
    {"quality": "best", "height": 1080, "ext": "mp4", "filesize_bytes": 12345678},
    {"quality": "720p", "height": 720, "ext": "mp4", "filesize_bytes": 7654321}
  ]
}
```

Preview uses the same YouTube URL allowlist as job creation. File sizes and video qualities are best-effort; playlists may expose less exact format data until each item is processed.

2) Create a job:
```bash
curl -X POST "http://127.0.0.1:8000/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"https://www.youtube.com/watch?v=dQw4w9WgXcQ\",\"mode\":\"audio\",\"quality\":\"best\"}"
```

Response:
```json
{
  "job_id": "3136209e-...",
  "status": "queued",
  "reused": false
}
```

3) Poll status:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/jobs/<job_id>"
```

Response (for playlists):
```json
{
  "job_id": "3136209e-...",
  "status": "succeeded",
  "playlist_total": 12,
  "playlist_succeeded": 11,
  "playlist_failed": 1,
  "output_filename": "result.zip",
  "output_type": "zip"
}
```

4) Download when `status == "succeeded"`:
```bash
curl -L -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/jobs/<job_id>/download" \
  -o output.bin
```

---

## Cancel a Running/Queued Job

You can cancel an active job:

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://127.0.0.1:8000/jobs/<job_id>/cancel"
```

Behavior:
- `queued` -> transitions to `canceled` immediately.
- `running` -> marked as cancel-requested, then transitions to `canceled` once the worker stops safely.
- `succeeded` / `failed` -> cancel is rejected with `409`.

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
- Progress is a **best-effort** approximation. For playlists, the `stage` field indicates item position (e.g., `downloading item 3/25`).
- Summary fields (`playlist_total`, etc.) are available via the Job status API once processing is complete.
- `eta_seconds` and `speed_bps` are reported when available; during post-processing they may be `null`/`0`.

---

## Metadata Embedding (Tags + Cover Art)

When enabled (`EMBED_METADATA=true`, `EMBED_THUMBNAIL=true`):
- Audio output (MP3) will include tags and embedded cover image (where supported by your media player).
- Video output may include metadata and embedded thumbnail depending on container and player.

- **Filenames**: Output filenames prefer `Artist - Title` when yt-dlp provides music metadata, then fall back to the readable YouTube title with Windows-safe sanitization.
- **Title Parsing**: For some single-video content, the system attempts to split "Artist - Title" to improve metadata accuracy. This is best-effort only: if lightweight probing cannot provide enough metadata, the job continues with `split_title=false` instead of failing before download.

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
- `OUTPUTS_TTL_MINUTES` (when `> 0`, overrides hours)
- `OUTPUTS_CLEANUP_INTERVAL_MINUTES`

---

## Optional: Cookies for Legitimate Authenticated Access

Some content may require authentication (private/unlisted/age-gated content or personal access).

For YouTube, cookies may need to be refreshed periodically because browser sessions can expire or be rotated. Export cookies in Netscape `cookies.txt` format from a browser where you are legitimately signed in.

You may provide a cookies file path via `.env`:

```env
COOKIES_FILE=C:\path\to\cookies.txt
```

Security notes:
- **Do not commit cookies**.
- Cookies are treated as **sensitive credentials**; never share them and do not store them in the repository.
- Prefer storing them in a secure path outside the project directory.
- The backend copies cookies to a per-job temporary file and ensures its deletion immediately after processing.

---

## Troubleshooting

### FFmpeg not found
- Windows: ensure `backend/bin/ffmpeg.exe` exists, or install FFmpeg globally and ensure it is on `PATH`.
- Linux/Docker: ensure both `ffmpeg` and `ffprobe` are installed and available on `PATH`.

### 401 Unauthorized
- Login again and ensure you send `Authorization: Bearer <token>`.

### 429 Too many active jobs
- You hit the per-user active job quota. Wait for queued/running jobs to finish, or increase `MAX_ACTIVE_JOBS_PER_USER`.

### Too many retry attempts on download errors
- `MAX_ATTEMPTS` controls the worker retry count.
- `YTDLP_RETRIES`, `YTDLP_FRAGMENT_RETRIES`, and `YTDLP_EXTRACTOR_RETRIES` control yt-dlp internal retries.
- The worker does not retry permanent errors such as unsupported URLs, invalid mode/quality, unavailable/private/age-restricted videos, missing cookies/auth, copyright blocks, and unavailable requested formats.

### YouTube download fails with 403, empty file, format unavailable, or n challenge errors

YouTube may require yt-dlp to solve JavaScript challenges before media URLs can be downloaded.

Ensure:
- Node.js is installed and available as `node`.
- yt-dlp is up to date.
- The backend enables yt-dlp JavaScript challenge support with Node.js. In Docker, `NODE_PATH=/usr/bin/node` is set by default.
- If yt-dlp warns that the local EJS solver is outdated or skipped, enable remote solver components with `YTDLP_REMOTE_COMPONENTS=ejs:github` (or `YTDLP_REMOTE_COMPONENTS=true`).
- If using authenticated access, `COOKIES_FILE` points to a valid Netscape-format `cookies.txt`.
- Cookies are refreshed if yt-dlp reports that account cookies are no longer valid.

In Docker production, rebuild the backend image after dependency changes:

```bash
docker compose build --no-cache backend
docker compose up -d
```

### Job succeeded but download fails
- Check `output_filename`/`output_type` in `GET /jobs/{job_id}`.
- Confirm the outputs directory exists and TTL cleanup hasn't removed it.

### Job failed with ALL_ITEMS_FAILED
- This means every item in the playlist encountered an error.
- Download the detailed report via `GET /jobs/{job_id}/report` to see per-item failure reasons.

### Playlist partially succeeded
- The `result.zip` contains only the successful items.
- Check `report.json` (inside the ZIP or via the `/report` endpoint) to see which items failed and why.
- Each playlist item is selected by its item-specific filename prefix, so a later item cannot be counted as successful by accidentally reusing a file from an earlier item.

---

## Development Notes

- Logs are printed to stdout.
- SQLite DB is stored at `data/app.sqlite` by default.
- Concurrency and queue sizing are controlled via env vars.

---

## Roadmap (Optional Ideas)
- `GET /jobs/{job_id}/log` endpoint (serve job.log safely)
- Expose granular per-item statuses in the jobs API
- Optional storage backends (S3/local network path)

---

## Legal Disclaimer

**This project is provided for educational and research purposes only.**

By accessing, downloading, or using this software, you explicitly agree to the following terms:

1.  **Compliance:** You are solely responsible for ensuring that your use of this software complies with all applicable local, state, and federal laws, as well as the Terms of Service of any third-party platforms (including but not limited to YouTube, YouTube Music, and Google).
2.  **No Liability:** The developer ("adirkoko") assumes **no liability** for any misuse of this software, including but not limited to copyright infringement, account suspensions, or legal actions taken against the user.
3.  **"As Is" Basis:** This software is provided "as is", without warranty of any kind, express or implied. The entire risk as to the quality and performance of the software is with you.

**Use this tool responsibly and respect the rights of content creators.**

## Acknowledgements & Third-Party Licenses

This project leverages powerful open-source tools. We gratefully acknowledge their contributions:

* **[yt-dlp](https://github.com/yt-dlp/yt-dlp):** A feature-rich command-line audio/video downloader (Unlicense/Public Domain).
* **[FFmpeg](https://ffmpeg.org/):** A complete, cross-platform solution to record, convert and stream audio and video (LGPL v2.1+).
* **[FastAPI](https://fastapi.tiangolo.com/):** A modern, fast web framework for building APIs with Python (MIT License).

*The names and logos of third-party services are property of their respective owners.*
