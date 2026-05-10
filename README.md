# MediaFlow

MediaFlow is a small full-stack tool for authorized users to preview YouTube links, choose audio or video output, process downloads in the backend, and track job progress from a clean one-page UI.

## Components

- `backend/`: FastAPI service for auth, admin users, quotas, jobs, download processing, and usage tracking.
- `frontend/`: Vite-built one-page web UI (served by nginx in Docker) with URL preview, format selection, live job status, and recent downloads.

## Documentation

- [backend/README.md](./backend/README.md): backend API, processing behavior, local backend development, and troubleshooting.
- [frontend/README.md](./frontend/README.md): frontend architecture, Vite development, runtime config, Docker build, and cache behavior.
- [DEPLOY.md](./DEPLOY.md): Ubuntu deployment steps.

For production on Ubuntu, this repo is designed to run with a single compose stack:
- [docker-compose.yml](./docker-compose.yml)
- [.env.production.example](./.env.production.example)
- [DEPLOY.md](./DEPLOY.md)

## Production (Ubuntu Server)

1. Copy env template:
```bash
cp .env.production.example .env
```

2. Set required values in `.env`:
- `MEDIAFLOW_JWT_SECRET`
- `MEDIAFLOW_CORS_ORIGINS`
- `HOST_MEDIAFLOW_DATA_ROOT`

Optional download-processing settings include:
- `MEDIAFLOW_NODE_PATH` to point yt-dlp at a custom `node` executable. Leave empty to use `node` from `PATH`.
- `MEDIAFLOW_YTDLP_REMOTE_COMPONENTS` to opt in to remote yt-dlp components such as `ejs:github`; `true` is accepted as an alias for `ejs:github`.
- `MEDIAFLOW_PUBLIC_URL` to make social link preview images absolute (for example `https://mediaflow.example.com`).

3. Start stack:
```bash
docker compose --env-file .env up -d --build
```

4. Verify:
```bash
docker compose ps
curl http://127.0.0.1:18080/health
```

Frontend will be available on `http://<server-ip>:8080` (default).

## Persistent Data Layout

Recommended homelab structure:
- `/srv/services/mediaflow` -> repository + compose files
- `/srv/data/mediaflow` -> persistent data outside the repo

Compose maps host paths to container paths:
- `/srv/data/mediaflow/backend-data` -> `/var/lib/mediaflow/data`
- `/srv/data/mediaflow/outputs` -> `/var/lib/mediaflow/outputs`
- `/srv/data/mediaflow/secrets` -> `/var/lib/mediaflow/secrets` (read-only)

## Runtime Configuration

The main production knobs are in [.env.production.example](./.env.production.example). Notable settings include:
- `MEDIAFLOW_API_BASE` for the frontend runtime API base, usually `/api`.
- `MEDIAFLOW_PUBLIC_URL` for absolute social preview metadata.
- `MEDIAFLOW_NODE_PATH` and `MEDIAFLOW_YTDLP_REMOTE_COMPONENTS` for yt-dlp YouTube processing behavior.
- `MEDIAFLOW_LOGIN_*` and `MEDIAFLOW_JOB_*_RATE_LIMIT_PER_MINUTE` for backend anti-abuse controls.
