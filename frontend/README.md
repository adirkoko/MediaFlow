# MediaFlow Frontend

The MediaFlow frontend is a Vite-built single-page web UI served by nginx in Docker. It keeps the same user flow as the static version, but the code is split into maintainable modules and production builds emit hashed assets for safe browser caching.

## Features

- One-page flow for login, link preview, output selection, job progress, recent jobs, and download actions.
- YouTube preview before job creation, including title, thumbnail, basic metadata, and available video qualities when the backend can resolve them.
- Audio/video selection with `quality=best` for audio and explicit quality choices for video.
- Live job progress through the backend SSE endpoint.
- Contextual inline errors for auth, preview, jobs, and the selected job.
- Copy Job JSON action with a short toast confirmation.
- Open Graph/Twitter metadata, favicon, home-screen icons, and web manifest assets.

## Tech Stack

- Vite
- Plain JavaScript ES modules
- Tailwind CSS compiled locally through PostCSS
- nginx for the production container

Node.js `20.19+` is recommended locally. The production Docker image uses Node 22 for the build stage.

## Project Layout

```text
frontend/
  index.html
  src/
    main.js
    config.js
    session.js
    state.js
    auth.js
    preview.js
    api/
      client.js
    jobs/
      helpers.js
      index.js
    styles/
      main.css
    ui/
      elements.js
      messages.js
      progress.js
    utils/
      format.js
  public/
    runtime-config.js
    assets/
      favicon.svg
      icon-192.png
      icon-512.png
      og-image.png
      site.webmanifest
  nginx/
    default.conf
  docker-entrypoint.d/
    40-runtime-config.sh
```

## Local Development

Install dependencies:

```bash
cd frontend
npm install
```

Run Vite:

```bash
npm run dev
```

The dev server runs on `http://127.0.0.1:5173` and proxies `/api/*` to `http://127.0.0.1:8000/*`, so run the backend locally as well.

## Production Build

```bash
cd frontend
npm run build
```

The output is written to `frontend/dist`. Vite emits JS/CSS under `dist/static` with hashed filenames, which prevents stale browser cache issues after deployment.

## Runtime Configuration

The frontend reads `window.MEDIAFLOW_API_BASE` from `/runtime-config.js`.

- Local Vite development uses [public/runtime-config.js](./public/runtime-config.js).
- Docker production generates `/runtime-config.js` at container startup from `MEDIAFLOW_API_BASE`.
- The default production value is `/api`, and nginx proxies `/api/*` to the backend container.

For social link previews, set `MEDIAFLOW_PUBLIC_URL` in the compose environment. The frontend entrypoint uses it to replace Open Graph/Twitter image URLs in `index.html`.

## Docker and Cache Behavior

The production image is a multi-stage build:

1. Node builds the Vite app.
2. nginx serves the generated `dist` directory.

nginx cache rules:

- `/index.html` and `/runtime-config.js`: no aggressive cache.
- `/static/*`: long immutable cache, safe because filenames are hashed.
- `/assets/*`: modest cache for favicon, manifest, and share images.

## IDE Notes

`node_modules` and `dist` are generated folders and should not be edited. The workspace settings hide them and disable TypeScript project-wide diagnostics so dependency `tsconfig.json` files do not show unrelated errors in VS Code.

If dependency diagnostics are already visible, close any open files under `frontend/node_modules` and run `Developer: Reload Window`.
