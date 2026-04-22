# AGENTS.md

## Purpose

This repository is **Airwave**: a FastAPI backend plus a Vue/Vite frontend that exposes one shared live MP3 stream for all connected clients. Users can add single YouTube URLs or playlist URLs into a shared queue, Sonos devices consume the same stream URL as browsers, and browsers can also connect as **SendSpin clients** for **synchronized playback**.

Airwave can also be paired with **WLED Sound Reactive** to sync lights to the stream (external integration; not a built-in lighting controller).

Use this file as the default working guide for code agents in this repo. Keep changes small, targeted, and easy to verify.

## Stack

- Backend: Python 3.10+, FastAPI, SQLAlchemy, Jinja2, `soco`
- Frontend: Vue 3, Vue Router, Vite, `@nuxt/ui`
- Runtime tools: `yt-dlp`, `deno`, `ffmpeg`
- Storage: SQLite by default via `AIRWAVE_DB_URL`

## Repository Map

- `app/main.py`: app factory, shared service wiring, startup lifecycle
- `app/api/routes.py`: HTTP and websocket endpoints, request models, response shaping
- `app/api/sendspin/routes.py`: SendSpin control/status endpoints
- `app/core/config.py`: environment-backed settings and public stream URL logic
- `app/db/repository.py`: persistence and queue/history/playlist database operations
- `app/services/playlist_service.py`: URL ingestion, playlist preview/import, queue construction
- `app/services/sendspin_service.py`: SendSpin server + synchronized playback integration
- `app/services/stream_engine.py`: playback loop and shared stream state
- `app/services/yt_dlp_service.py`: YouTube metadata, playlist inspection, source resolution
- `app/services/sonos_service.py`: Sonos discovery and control
- `frontend/src/App.vue`: root UI state orchestration
- `frontend/src/components/`: UI panels and reusable Vue components
- `frontend/src/composables/useApi.js`: shared fetch helper for frontend API calls
- `frontend/src/composables/useSendspinPlayer.js`: browser SendSpin player/controller client
- `app/templates/index.html`: server-rendered shell that hosts the frontend build
- `app/static/dist/`: built frontend assets served by FastAPI
- `scripts/run_dev.sh`: local dev launcher; builds frontend assets if needed, then runs `uvicorn`
- `tests/`: Python tests
- `tests_e2e/`: end-to-end browser coverage

## Working Agreements

- Preserve the shared-stream model. Do not accidentally turn `/stream/live.mp3` into a per-client stream.
- Keep route, service, and repository responsibilities separated:
  - `routes.py` should validate input, call services/repository methods, and shape API responses.
  - `services/` should contain business logic and orchestration.
  - `repository.py` should own database read/write behavior.
- Prefer extending existing helpers and serializers before adding parallel code paths.
- Avoid unrelated refactors when fixing one behavior.
- Keep API payload shapes stable unless the task explicitly requires a contract change.
- Follow existing naming and style in the touched file instead of normalizing the whole codebase.

## Run And Test

### Initial setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install ".[dev]"
npm install
./scripts/setup_yt_dlp.sh
./scripts/setup_deno.sh
```

Optional:

```bash
./scripts/setup_ffmpeg.sh
```

### Local development

```bash
./scripts/run_dev.sh
```

This script activates `.venv` when present, builds frontend assets if `app/static/dist/app.js` is missing, then starts:

```bash
uvicorn app.main:create_app --factory --reload --no-access-log
```

### Common validation

- Test execution rule (match `README.md`):
  - Activate virtualenv first: `source .venv/bin/activate`
  - Ensure dev deps are installed: `python -m pip install ".[dev]"`
  - Then run tests with venv Python: `python -m pytest`
  - Do not assume global `python`/`pytest` exists outside `.venv`.
- Backend tests: `python -m pytest`
- Frontend build check: `npm run build`
- Frontend dev server when needed: `npm run dev`
- Frontend preview when needed: `npm run preview`

If you change Vue files, composables, or router behavior, run `npm run build` so `app/static/dist` stays in sync with the served app.

## Backend Conventions

- Add new HTTP schemas near related endpoints in `app/api/routes.py` using Pydantic models.
- Reuse the existing request-app-state pattern instead of creating ad hoc globals. Routes currently access shared services through `request.app.state`.
- Keep response serialization consistent with the existing `_serialize_*` helpers in `app/api/routes.py`.
- Queue and playlist ingestion logic belongs in `PlaylistService`, not directly in route handlers.
- YouTube resolution and playlist inspection belong in `YtDlpService`.
- Database mutations should flow through `Repository` methods and typed helper objects such as `NewQueueItem` and `NewPlaylistEntry`.
- Environment-dependent behavior should be driven through `app/core/config.py` and `AIRWAVE_*` variables rather than hardcoded paths or URLs.
- Be careful with long-running or streaming code. Client disconnects and shutdown behavior are expected cases, not exceptional failures.

## Frontend Conventions

- `frontend/src/App.vue` is the main coordinator for queue, history, playlists, playback state, and Sonos state. Avoid duplicating global state in multiple components.
- Use `fetchJson` from `frontend/src/composables/useApi.js` for API requests unless there is a strong reason not to.
- Keep presentational logic inside components and shared request/state utilities inside composables.
- Prefer keeping UI action logic in the component that renders the control when behavior is local to that component; emit events when parent coordination is required for shared state, navigation, or cross-component side effects.
- Match the existing Vue style in touched files. Current code uses `<script setup>`, double quotes, and composition API primitives.
- When adding UI that depends on backend payloads, verify the shape against the API response instead of assuming fields.
- Use in-app modals (e.g. `UModal`) for confirmations and editing flows. Do not use browser `confirm()`, `alert()`, or `prompt()` so that UX stays consistent with the rest of the app.

### Frontend Theme System

- Theme styles live under `frontend/src/css/`:
  - Shared/global stylesheet: `frontend/src/css/style.css`
  - Per-theme files: `frontend/src/css/themes/*.css`
- Prefer adding a **new theme file** in `frontend/src/css/themes/` over growing one large monolithic CSS file.
- Keep each theme self-contained with variables for:
  - App shell/surfaces (`--app-*`)
  - Nuxt UI tokens (`--ui-*` and `--ui-color-*`) so `UButton`, `UTabs`, and related components change with the selected theme.
- Theme state is managed by `frontend/src/composables/useTheme.js` and persisted in local storage under `airwave:settings:theme`.
- Current theme names:
  - `night`: legacy/current theme
  - `dark`: new default theme when no saved preference exists
- Theme selection UI lives at `frontend/src/pages/settings.vue`.
- When adding a new theme:
  - Create `frontend/src/css/themes/<theme-name>.css`
  - Import it from `frontend/src/css/style.css`
  - Add it to `supportedThemes` in `frontend/src/composables/useTheme.js`
  - Expose it in the `/settings` theme selector

## Change Guidance

- For backend-only changes:
  - Prefer targeted tests in `tests/`.
  - Verify that queue, history, playlist, and stream-related payloads remain backward compatible.
- For frontend-only changes:
  - Build the frontend and check for runtime errors in the rendered app.
  - Remember that FastAPI serves built assets from `app/static/dist`, not directly from `frontend/src`.
- For cross-stack changes:
  - Update both the API contract and the consuming Vue code in the same change.
  - Manually sanity-check the user flow end to end if it touches queueing, playback state, playlists, or Sonos controls.

## Safety Checklist

Before finishing work:

- Run the smallest relevant validation command for the files you changed.
- If frontend code changed, run `npm run build`.
- If backend behavior changed, activate `.venv` and run `python -m pytest` (or a focused subset) with the virtualenv Python.
- Call out any validation you could not run.
- Do not edit generated/built output manually unless the task specifically requires it.
- Do not commit local secrets, `.env` contents, binaries, or database files unless the user explicitly asks for that.
