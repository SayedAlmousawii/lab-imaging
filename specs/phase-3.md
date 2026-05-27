# Phase 3 — Local Web Dashboard

This is the authoritative spec for Phase 3 work. It consolidates the
Phase 3 section of `05_BUILD_PLAN.md` with the architecture's
"local-only dashboard" stance from `02_ARCHITECTURE.md` and the web
module layout from `03_PROJECT_STRUCTURE.md`. If anything in the broader
specs contradicts this file for Phase 3 scope, this file wins for Phase 3.

## Goal

Make the engine usable by lab staff without a terminal. A browser-based
dashboard on `http://localhost:<port>` (optionally LAN-reachable) lets
the operator pick a camera, snap a fresh preview, configure an
experiment, start it, watch the status of all stations, view the latest
captured frame, and stop early.

## Framework choice

**Use Flask.** Pin a recent stable release in `requirements.txt`. Reasons:
- The dashboard is local, low-traffic, synchronous request/response. No
  websocket fan-out, no streaming, no high-concurrency need.
- Smaller dependency tree than FastAPI (no Pydantic, no Starlette, no
  ASGI server). Easier to install on a Windows lab machine.
- Synchronous Python interacts cleanly with the engine's threading model
  (capture lock + scheduler thread). FastAPI's async story would invite
  async/sync mixing bugs in code paths where the engine is firmly
  synchronous.

If a future feature genuinely needs async (e.g., server-sent events for
live status), revisit then. For v1, Flask.

This choice is logged in `DECISIONS.md` at the time Phase 3 begins.

## Deliverables

1. **`labcam/web/server.py`** — Flask app with the routes below. Talks
   to the engine API from Phase 2; never imports `cv2`.

2. **`labcam/web/templates/`** — two HTML screens, plain Jinja:
   - `status.html` — table of all stations with their current state.
   - `new.html` — new-experiment form with camera dropdown, name,
     interval, duration, operator, notes, Preview button, Start button.
   - A shared `base.html` for layout if helpful.

3. **`labcam/web/static/`** — plain CSS and a small amount of vanilla
   JS. No front-end framework, no build step, no bundler.

4. **`labcam/main.py`** — entry point. Loads `config/settings.json`
   (creating it from `settings.json.example` if missing), refuses to
   start if `config/cameras.json` is missing (point operator at
   `tools/camera_setup.py`), runs the engine startup-recovery routine,
   starts the scheduler thread, starts the Flask server. One command:
   `python -m labcam.main`.

## Routes

All routes are local-only by default. Bind to `127.0.0.1` unless
`allow_lan_access` is true in `settings.json`, in which case bind to
`0.0.0.0`. No auth in v1 — document this in the README.

### Pages
- `GET /` — `status.html`.
- `GET /new` — `new.html`.

### JSON API (called by the page JS)
- `GET /api/cameras` → list of camera labels + identity strategy +
  warnings (from `config/cameras.json`). The dashboard surfaces
  warnings prominently — e.g., a yellow badge on any station whose
  `identity_strategy` is not `hardware_id`.
- `POST /api/preview` body `{camera_label}` → captures a fresh still
  through the capture lock and returns the image (either inline as
  JPEG bytes, or a URL to a temp file). **Same code path as a
  scheduled capture.** Disabled (returns 409) if any experiment is
  currently mid-capture on the same camera — the lock will serialize,
  but the UI should not let the user spam previews on a busy station.
- `POST /api/experiments` body `{camera_label, name, interval_minutes,
  duration_hours, operator, notes}` → starts an experiment. Returns
  the new `experiment_id` or a structured error
  (`camera_busy` / `baseline_failed` / `disk_full` /
  `invalid_name` / etc.).
- `POST /api/experiments/<id>/stop` → early stop. Returns final state.
- `GET /api/status` → array of every station with current state
  (idle / running / finished). For running stations: experiment name,
  elapsed, images captured, time remaining, next-capture time.
- `GET /api/experiments/<id>/latest` → most recent captured JPEG (or
  404 if none yet). Used by the status view to show a thumbnail of
  the latest frame.

## UI requirements

- **Status view (`/`):** one row per camera label from
  `config/cameras.json`. Shows label, status, identity-strategy badge
  (with warning style for non-`hardware_id`), and for running
  stations: experiment name, elapsed, images captured, time
  remaining, a thumbnail of the latest frame (auto-refresh ~10 s),
  and a **Stop** button. Polling (not websockets) is fine.
- **New-experiment panel (`/new`):** form with sane defaults from
  `settings.json` (`default_interval_minutes`,
  `default_duration_hours`). Camera dropdown lists labels from
  `cameras.json`. **Preview** button hits `/api/preview` and shows the
  returned JPEG inline before the user commits to **Start**. Validation:
  sanitized name, interval > 0, duration > 0, camera not busy.
- **No editing experiments after start.** The form is one-way: start it
  or don't.
- **Plain HTML/CSS/JS.** Keep it readable. The UI is small; do not
  add frameworks.

## Constraints (Phase 3)

- **`web/` never imports `cv2`.** All camera access is via engine /
  `labcam/cameras/` APIs.
- **`web/` never branches on OS.**
- **The preview path is `labcam.cameras.preview_frame()`** through the
  same process-wide capture lock used by scheduled captures. Phase 3
  must not introduce a second capture code path.
- **Local-only by default.** LAN access is opt-in via `settings.json`
  and prints a warning at startup.
- **No auth.** Document the LAN-access security implication in the
  README.
- **No database, no session store.** The engine and `cameras.json`
  are the only state.

## Testing (Phase 3)

- **Full workflow in a browser on the Mac dev machine:** open `/new`,
  pick a camera, name an experiment, preview, start. Switch to `/`,
  see it running. Wait for a couple of captures, see the thumbnail
  update. Stop early. Confirm the folder on disk matches.
- **Two concurrent experiments started from the UI** — confirm
  staggering still works (per Phase 2 test #2, but driven via the UI).
- **Preview while another experiment is mid-capture** — confirm the
  lock serializes correctly and the UI handles the brief wait or 409.
- **Refuse to start a second experiment on a busy camera** — UI shows
  a clear error.
- **LAN access opt-in:** flip the setting, restart, hit the dashboard
  from a phone/laptop on the same Wi-Fi.

## Out of scope for Phase 3

- Auth, HTTPS, multi-user — future hardening if LAN access is ever
  used beyond a trusted lab network.
- Live MJPEG / WebRTC video preview — not in v1, ever.
- Editing a running experiment's interval/duration — not in v1.
- Windows-specific testing — Phase 4.
- A separate "lab staff" README — Phase 5.

## Definition of done

- `python -m labcam.main` starts the engine + server in one command.
- A non-technical user can complete the full workflow (preview →
  start → monitor → stop / auto-complete) entirely from a browser.
- The four UI test scenarios pass.
- No `cv2` imports outside `labcam/cameras/`. No OS branching
  outside `labcam/cameras/`.
- `requirements.txt` updated with Flask pin.
- `HANDOFF.md` updated; framework choice logged in `DECISIONS.md`.
