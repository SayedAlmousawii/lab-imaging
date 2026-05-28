# Phase 3.5 — Dashboard UI Polish / Redesign

This is the authoritative spec for Phase 3.5 work. Phase 3 shipped a
functional dashboard built on a plain HTML `<table>` and a native
`<select>` camera picker; Phase 3.5 ports a high-fidelity redesign
into the existing Flask app **without changing capture behaviour or
route contracts**. The Claude Design export may exist locally under
`design_handoff_lab_imaging/` as a reference-only artifact, but that
folder is gitignored because its prototype HTML/JS may use CDN
dependencies that are not part of the runtime dashboard.

If anything in `specs/phase-3.md` contradicts this file for the
UI surface, this file wins for Phase 3.5. Backend contracts in
`specs/phase-3.md` (routes, polling cadence, debounce timings,
validation rules) remain authoritative. Phase 3.5 may add
display-only fields to existing JSON payloads when needed by the
redesigned UI.

## Goal

A scientific-instrument-feeling dashboard the lab can leave open on a
benchtop monitor across the room and read at a glance — without
changing a line of backend code.

## Hard constraints (carried from Phase 3)

- `web/` never imports `cv2`. Verified by `rg "import cv2|from cv2"
  labcam tools` returning only `labcam/cameras/base_capture.py`.
- `web/` never branches on OS. Verified by `rg
  "platform\.system|sys\.platform|os\.name" labcam tools` returning
  only `labcam/cameras/interface.py`.
- All Flask routes from Phase 3 are unchanged. No new endpoints. No
  engine changes. `/api/status` may include additive display-only
  fields such as `interval_minutes` and `ended_at`.
- No build step. No bundler. No JS framework. No CSS framework.
- No Python dependency added. `requirements.txt` is untouched.
- No CDN dependency at runtime. The dashboard works fully offline.

## New constraint (Phase 3.5)

- Two self-hosted webfonts ship under `labcam/web/static/fonts/`:
  `InterVariable.woff2` and three weights of JetBrains Mono
  (`Regular`, `Medium`, `SemiBold`). Both fonts are SIL OFL 1.1; the
  license text lives next to the font files at
  `labcam/web/static/fonts/OFL.txt`.

## Deliverables

1. **`labcam/web/static/styles.css`** — replaced wholesale with the
   handoff CSS, prefixed with `@font-face` blocks pointing at the
   self-hosted woff2 files.

2. **`labcam/web/static/fonts/`** — `InterVariable.woff2`,
   `JetBrainsMono-Regular.woff2`, `JetBrainsMono-Medium.woff2`,
   `JetBrainsMono-SemiBold.woff2`, and `OFL.txt`.

3. **`labcam/web/templates/base.html`** — `.topbar` chrome
   (`brand-mark`, nav with `is-active` driven by `request.endpoint`,
   live indicator with `#last-refresh` hook).

4. **`labcam/web/templates/status.html`** — `page-head` heading +
   `summary` strip (4 cells) + `station-grid` container. All filled
   client-side by `status.js`.

5. **`labcam/web/templates/new.html`** — `config-grid` two-column
   layout. Left `.card` holds the form with `.cam-picker` (replaces
   native `<select>`; hidden `<input type="hidden" name="camera_label">`
   preserves `POST /api/experiments` body shape), `.input-group`s
   with `.unit` suffix for interval/duration, `.run-summary` in the
   `.card-foot`. Right `<aside class="preview">` holds the live
   preview panel with `.ph-frame` states (`is-empty` / `is-loading` /
   `is-success` / `is-error`).

6. **`labcam/web/static/status.js`** — rewritten to render
   `<article class="station" data-state="…">` per the design's
   `StationCard`. Adds:
   - `clientState(station)` mapper: `running` / `idle` / `done` /
     `error` / `offline`. Today's engine only emits idle / running /
     finished; the mapper supports future `error` / `offline` states
     without fabricating them.
   - `renderSummary(stations)` for the 4-cell summary strip.
   - `updateLastRefreshLabel()` for the live indicator.
   - Per-second tick for "Next in mm:ss" countdowns inside running
     station cards.
   - Preserves `STATUS_REFRESH_MS = 10000` and
     `THUMBNAIL_REFRESH_MS = 3000` unchanged.

7. **`labcam/web/static/new.js`** — rewritten to render `.cam` rows
   into a hidden input, contextual `.note` banners under the picker
   / name input / form footer, and `.ph-frame` state transitions for
   preview. Adds:
   - `updateRunSummary()` — pure client-side:
     `frames = floor(duration_h*60 / interval_m)`, finish ETA = now +
     duration, storage estimate = `frames * 0.05 MB`. The 0.05 figure
     is from a fresh measurement of existing Phase 2/3 JPEG captures
     (~45 KB/frame), not the handoff's 0.3 MB placeholder.
   - Camera picker keyboard support: the selected idle row is the
     tab stop, busy rows stay disabled, Enter/Space selects, arrow
     keys move and select among idle rows, and Home/End jump to the
     first/last idle camera.
   - After a successful start, suppresses the duplicate-name warning
     for that exact just-started camera/name until the user edits the
     name or changes cameras; stale-tab server errors still show.
   - Preserves `validatePayload()`, name-check debounce (250 ms),
     and the `camera_busy` → reload-camera-list recovery from Phase 3.

## Out of scope

- Tracking `design_handoff_lab_imaging/` in git. It is a local
  reference artifact only; the app runtime must remain the Flask /
  Jinja / vanilla JS implementation under `labcam/web/`.
- `error` / `offline` station states are never rendered by the
  current engine; the client-side mapper supports them but does not
  fake them. Server-side emission is a later phase.
- `Cache-Control: no-store` + `ETag` on `/api/experiments/<id>/latest`
  is a deferred backend optimisation (the handoff suggested it; not
  in this phase).
- Camera labels stay verbatim from `config/cameras.json`. No
  `station1` → `Station 01` renaming.
- Dark mode, history view, capture-cadence charts — out of scope per
  the handoff itself.

## Testing (Phase 3.5)

All Phase 3 functional tests must still pass against the new UI:

1. Full workflow on real hardware: `/new` preview → start → switch to
   `/` → see running card with frame thumbnail refreshing every 3 s →
   "Next in mm:ss" counts down → Stop early → card flips to
   `data-state="done"`.
2. Two concurrent experiments started from the UI run on
   `station1`+`station2`; both cards show running with thumbnails.
3. Preview button on a camera with an active scheduled run returns
   the inline `.note.is-danger` under the picker (not a top-of-page
   banner).
4. Stale tab: starting in tab A locks the picker in tab B on the
   next submit, with `.note.is-danger` and the picker row marked
   `.is-busy`.
5. Duplicate name today on the selected camera shows
   `.note.is-warn` under the name input naming the exact suffixed
   folder.

## Definition of done

- All Phase 3 functional tests above pass against the redesigned UI.
- Visual review against the local Claude Design reference, when
  available, matches on topbar, page-head, summary strip, station card
  chrome, cam-picker, input-group, run-summary, and preview panel
  states.
- All Phase 3.5 hard constraints hold (no cv2 leaks, no OS branching,
  no new Python deps, no CDN dependency).
- `HANDOFF.md`, `DECISIONS.md`, `specs/05_BUILD_PLAN.md`, and
  `README.md` are updated.
