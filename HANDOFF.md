# HANDOFF.md — Live Project Status

State only. No rules. Rules live in `AGENTS.md`.

Every session updates this file as its last action, even if nothing
changed (write "no changes this session" explicitly under that date).

---

## Current state

- **Current phase:** Phase 6 — dashboard workflow features. Phase 5 is
  considered complete by the human. Phase 6 Task 1 through Task 9,
  including dashboard hot-plug detection, detected-preview, stale
  camera-row/preview/draft-input guards, the Settings page,
  configurable experiment save location, cloud-synced storage guidance,
  post-experiment notes, the read-only experiment browser, and
  maintenance mode with maintenance-only fresh-still preview are
  implemented locally. Task 9 is complete as a docs-only recommendation
  to keep preview as repeated fresh stills for the current Phase 6 path.
- **Current branch:** `phase-6-dashboard-workflows`.
- **Open questions:** none.
- **Known issues:** macOS AVFoundation also exposes a Continuity/iPhone
  camera at index 2; it is excluded from the current lab camera mapping.
  The Codex app process still lacks macOS camera permission, but the
  approved Terminal can run the real-camera driver successfully. Manual
  Terminal-hosted post-fix stale-row/hot-plug preview and draft-input
  validation is pending.
- **Next actions:** Human review of the completed Phase 6 Task 9
  recommendation. Optional future work should be a separate
  repeated-still UX spec, not production live-preview implementation.

---

## Session log

### 2026-05-27 — Project initialized

- Created git repository on `main`.
- Added `.gitignore` covering Python build artifacts, OS junk, editor
  folders, runtime output (`experiments/`), and the live config files
  (`config/cameras.json`, `config/running_state.json`,
  `config/settings.json`). `config/settings.json.example` is tracked.
- Moved the six planning docs from `context/` into `specs/`. Removed
  the now-empty `context/` directory.
- Added `specs/phase-1.md` as the authoritative Phase 1 reference
  (Phase 1 section of `05_BUILD_PLAN.md` + applicable clarifications
  from `02_ARCHITECTURE.md` and `03_PROJECT_STRUCTURE.md`).
- Seeded `DECISIONS.md` with the eight major decisions made during
  planning.
- Seeded `AGENTS.md` (persistent rulebook) and `HANDOFF.md` (this
  file).
- Initial commit on `main` contains only scaffolding (no code).
- Created and checked out branch `phase-1-camera-setup` for the next
  session's work.
- No remote configured. No push performed.

### 2026-05-27 — Phase 0 and Phase 1 camera setup implemented

- Built the Phase 0 skeleton: package directories, empty `__init__.py`
  placeholders, tracked web `.gitkeep` files, `requirements.txt`,
  developer `README.md`, and `config/settings.json.example`.
- Installed Python 3.11 with Homebrew because the shell only exposed
  system Python 3.9 initially. Created `.venv` with Python 3.11.15.
- Installed `opencv-python-headless==4.13.0.92`. The sanity check
  `.venv/bin/python -c "import cv2; print(cv2.__version__)"` printed
  `4.13.0`.
- Implemented Phase 1 camera layer files:
  `labcam/cameras/interface.py`, `labcam/cameras/base_capture.py`, and
  `labcam/cameras/identify_macos.py`.
- Implemented `tools/camera_setup.py` with list/setup/stress-test modes,
  temp-directory preview snapshots, sanitized labels, optional notes,
  and `config/cameras.json` output.
- Verified Python compilation with `.venv/bin/python -m compileall
  labcam tools`.
- Verified only `labcam/cameras/base_capture.py` imports `cv2`; no
  `cv2.imshow` calls exist in `labcam` or `tools`; `requirements.txt`
  does not contain plain `opencv-python`.
- Initial hardware validation was blocked because OpenCV camera access
  was denied for this terminal/app.
- Remote `origin` now exists and the branch tracks
  `origin/phase-1-camera-setup`; no push was performed this session.

### 2026-05-27 — Camera permission granted and target hardware tested

- Reset macOS camera permissions and ran the camera tools through
  Terminal after the human granted Terminal camera access.
- Found that macOS exposed three AVFoundation indexes: 0, 1, and 2.
  Indexes 0 and 1 are the target Mac test hardware; index 2 appears to
  be Continuity/iPhone-style camera input.
- Fixed Phase 1 macOS identity handling after live testing showed
  `system_profiler` metadata order can mismatch OpenCV index order.
  Multi-camera macOS enumeration now records `index_fallback` with loud
  warnings instead of assigning unsafe hardware IDs.
- Added `--indexes` filtering to `tools/camera_setup.py` so setup and
  stress tests can target the actual lab cameras when extra macOS
  virtual/continuity cameras are present.
- Regenerated ignored runtime `config/cameras.json` for indexes 0 and 1
  only:
  - `station1` -> index 0, `identity_strategy="index_fallback"`,
    notes `Logitech C310 HD WebCam`.
  - `station2` -> index 1, `identity_strategy="index_fallback"`,
    notes `Built-in FaceTime HD Camera`.
- Captured fresh preview snapshots for both mapped cameras to the OS
  temp directory.
- Ran `python tools/camera_setup.py stress-test --indexes 0 1 --cycles
  100` through Terminal. Result: 100/100 captures passed for index 0
  and 100/100 captures passed for index 1.
- A full all-index stress test failed on index 2 at cycle 1 with
  `Could not read frame from camera index 2`; this camera was excluded
  from the lab mapping.
- `config/cameras.json` remains ignored runtime config and was not
  staged. No push was performed.

### 2026-05-27 — Phase 2 capture engine implemented

- Updated local `main` from `origin/main` after Phase 1 was merged, then
  created and switched to branch `phase-2-capture-engine`.
- Implemented the headless capture engine:
  `labcam/engine/experiment.py`, `labcam/engine/storage.py`,
  `labcam/engine/state.py`, and `labcam/engine/scheduler.py`.
- Added typed engine failures for expected start errors, including
  active camera conflicts, missing camera config, disk-space preflight
  failure, baseline failure, and unknown experiment ids.
- Implemented file-only experiment storage with sanitized collision-safe
  folders, Windows-safe timestamped JPEG names, atomic `metadata.json`
  writes, append-only `capture_log.txt`, and atomic
  `config/running_state.json` management.
- Implemented Option A startup recovery: stale `running_state.json`
  entries finalize their experiment metadata with `end_reason="unknown"`
  and then clear the state file.
- Implemented scheduled capture retries and sequence gaps: scheduled
  failures log retry `ERROR` lines, log `failed after retries; sequence
  gap recorded`, increment the monotonic sequence, and continue the run.
- Implemented baseline-failure handling: the experiment folder is kept,
  metadata is finalized with `end_reason="baseline_failed"`,
  `images_captured=0`, and no running-state entry is added.
- Added `tools/phase2_driver.py` with all six Phase 2 scenarios and a
  `--mock-capture` mode for deterministic no-hardware validation.
- Corrected the real-camera overlap check in `tools/phase2_driver.py`:
  the first implementation measured time before `capture_frame()` had
  acquired the camera-layer lock, so waiting on the lock looked like a
  false overlap. The driver now avoids that false assertion for real
  camera mode.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches
  - `.venv/bin/python tools/phase2_driver.py --profile fast
    --mock-capture --cameras station1 station2` passed 6/6 scenarios
- Real-camera validation passed from approved Terminal:
  - `.venv/bin/python tools/phase2_driver.py --profile fast --cameras
    station1 station2` passed 6/6 scenarios.
  - `.venv/bin/python tools/phase2_driver.py --profile spec --cameras
    station1 station2` passed 6/6 scenarios.
- No push was performed.

### 2026-05-28 — Phase 3 Flask dashboard implemented

- Refreshed `origin`, confirmed local `main` matched `origin/main` at
  Phase 2 merge commit `ab7f352`, and created branch
  `phase-3-dashboard` from `main`.
- Implemented `labcam/main.py` as the `python -m labcam.main` entry
  point. It creates `config/settings.json` from the example if missing,
  refuses startup without `config/cameras.json`, runs startup recovery
  through `CaptureEngine`, starts the scheduler thread, and binds Flask
  to `127.0.0.1` unless `allow_lan_access` is true.
- Implemented the Phase 3 Flask dashboard in `labcam/web/server.py`,
  `labcam/web/templates/`, and `labcam/web/static/` using plain
  HTML/CSS/vanilla JS and no build step.
- Added JSON routes for cameras, preview, experiment start, early stop,
  station status, and latest-frame thumbnails.
- Added engine support for dashboard preview and status needs:
  `CaptureEngine.start()`, `CaptureEngine.list_cameras()`, and
  `CaptureEngine.preview()`. Preview uses
  `labcam.cameras.preview_frame()` and the same save path; scheduled
  capture bookkeeping now marks cameras as in-capture so same-camera
  previews return a busy error instead of queueing behind an active
  capture.
- Updated `requirements.txt` with `Flask==3.1.1` and documented the
  local/no-auth dashboard plus LAN-access warning in `README.md`.
- Browser UI validation passed from the macOS Terminal-hosted server
  because the Codex app process still lacks camera permission:
  - Full workflow: `/new` preview -> start -> `/` running status with
    thumbnail -> stop early -> experiment folder written.
  - Two concurrent experiments from the UI ran on `station1` and
    `station2`, both showing running status and thumbnails.
  - Preview while another station was running scheduled captures returned
    a fresh inline JPEG for the idle station.
  - Attempting to start a second experiment on the selected busy camera
    showed the clear UI error "That camera already has a running
    experiment."
- Filesystem check after UI validation found generated experiment
  folders under ignored `experiments/` with metadata, logs, and 105
  total JPEGs from the test runs.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches
- Screenshots saved outside the repo for this session:
  `/private/tmp/labcam-busy-camera-ui.png` and
  `/private/tmp/labcam-status-ui.png`.
- No push was performed.

### 2026-05-28 — Phase 3 dashboard notes fixed

- Fixed the confusing post-start busy-camera message on `/new`.
  Starting an experiment now preserves a neutral success message:
  "Experiment started. This camera is now running."
- Fixed busy-camera controls on `/new`. When the selected camera is
  running, Preview and Start are disabled and Start reads
  "Camera running"; selecting an idle camera restores both controls.
- Fixed stale-tab busy-camera handling. If another browser tab starts a
  camera after the form loaded, the server-side `camera_busy` response
  still shows as an error and the form refreshes camera availability so
  the selected running camera becomes locked.
- Added independent latest-frame thumbnail refresh on `/`: running
  station thumbnails re-request `/api/experiments/<id>/latest` every
  three seconds while the full status table keeps its ten-second poll.
  This remains repeated still-image fetching, not streaming.
- Browser validation passed on the Terminal-hosted real-camera server
  at port 5055:
  - Successful start kept the neutral success message and locked the
    selected running camera.
  - Switching the dropdown to the idle camera re-enabled Preview and
    Start.
  - Running station thumbnail `src` changed after the three-second
    thumbnail refresh interval, before the ten-second table poll.
  - A stale second tab submitted a now-busy camera, showed the
    server-side busy error, refreshed availability, and locked the
    selected running camera.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches
- Test experiments were stopped or naturally completed before the
  server was shut down. Runtime test output remains under ignored
  `experiments/`.
- No push was performed.

### 2026-05-28 — Duplicate experiment name warning added

- Confirmed duplicate experiment names do not overwrite existing data:
  storage creates a suffix such as `_2` or `_3` when the same
  date/name/camera folder already exists.
- Added `POST /api/experiments/name-check`, a read-only dashboard API
  that previews the folder name the next run would use without creating
  files.
- Updated `/new` to warn when the selected camera/name would reuse an
  existing date/name/camera base folder. The warning names the exact
  suffixed folder that will be created.
- Browser validation passed on the Terminal-hosted dashboard at port
  5055:
  - Entering duplicate `testtt` on `station1` showed
    `2026-05-28_testtt_station1_3`.
  - Entering a unique name cleared the warning.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches
- Screenshot saved outside the repo:
  `/private/tmp/labcam-duplicate-name-warning.png`.
- Dashboard was left running on port 5055 for the human to continue
  trying. No push was performed.

### 2026-05-28 — Phase 3.5 UI redesign ported

- Created branch `phase-3.5-ui-redesign` from `main` after Phase 3
  merge.
- Replaced `labcam/web/static/styles.css` with the Claude Design
  handoff stylesheet (845 lines, production-ready) and prepended
  `@font-face` blocks for self-hosted Inter (variable woff2) and
  three weights of JetBrains Mono (Regular/Medium/SemiBold) under
  `labcam/web/static/fonts/`. SIL OFL 1.1 license shipped alongside
  the fonts at `labcam/web/static/fonts/OFL.txt`.
- Rewrote `labcam/web/templates/base.html` with the `.topbar`
  chrome (brand mark, active-nav hook driven by `request.endpoint`,
  live indicator). Rewrote `labcam/web/templates/status.html` to
  emit `.page-head` + `.summary` strip + `.station-grid` container,
  with content filled client-side. Rewrote
  `labcam/web/templates/new.html` as a `.config-grid` two-column
  layout with `.card` form on the left (cam-picker, input-group
  units, run-summary, hidden `camera_label` input preserved) and
  `<aside class="preview">` panel on the right.
- Rewrote `labcam/web/static/status.js` to render
  `<article class="station" data-state="…">` cards per the
  handoff's `StationCard`. Added `clientState()` mapper (covers
  idle/running/done/error/offline; engine emits only the first
  three today), `renderSummary()`, `updateLastRefreshLabel()`, and a
  per-second tick for "Next in mm:ss" countdowns. Polling intervals
  (10 s status, 3 s thumbnail) preserved.
- Rewrote `labcam/web/static/new.js` to render `.cam` rows into a
  hidden input, contextual `.note` banners (warn / danger / info)
  under the picker, name input, and form footer, and `.ph-frame`
  state transitions (empty / loading / success / error) for the
  preview panel. `validatePayload()`, name-check 250 ms debounce, and
  the `camera_busy` recovery path from Phase 3 preserved. Added
  `updateRunSummary()`: frames = `floor(duration_h*60/interval_m)`,
  finish ETA = now + duration, storage estimate = `frames * 0.05 MB`
  (based on a fresh measurement of existing Phase 2/3 JPEGs at
  ~45 KB/frame, not the handoff's 0.3 MB placeholder).
- Backend untouched: no edits to `labcam/web/server.py`,
  `labcam/engine/`, `labcam/cameras/`, or `requirements.txt`.
- Created `specs/phase-3.5.md` (authoritative spec). Inserted
  Phase 3.5 in `specs/05_BUILD_PLAN.md`. Added a deferral note to
  `specs/phase-3.md`. Logged decisions #14 (adopt the redesign /
  self-host fonts) and #15 (0.05 MB/frame storage estimate) in
  `DECISIONS.md`. Updated `README.md` to note the self-hosted fonts
  and offline behaviour.
- Validation so far:
  - `.venv/bin/python -m compileall labcam tools` reported no
    errors.
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\.imshow" -n labcam tools` reports no matches.
  - `rg "platform\.system|sys\.platform|os\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches; `requirements.txt` unchanged.
- Browser hardware validation still pending — needs to be run from
  the approved Terminal session because the Codex app process still
  lacks macOS camera permission. No push performed.

### 2026-05-28 — Phase 3.5 status payload display fields added

- Added additive display-only fields to `/api/status` station objects
  when an experiment exists:
  - `interval_minutes`, copied from experiment metadata.
  - `ended_at`, emitted for finished experiments and `null` for
    running experiments.
- Updated the redesigned status cards to use `interval_minutes` for
  interval display and `ended_at` for the finished-card "Finished"
  metric, with graceful `—` fallback if either field is unavailable.
- Updated `specs/phase-3.5.md` to clarify that Phase 3.5 keeps
  routes and capture behaviour unchanged while allowing additive
  display-only fields on existing JSON payloads.
- Logged decision #16 in `DECISIONS.md` for additive `/api/status`
  display fields.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/status.js`
  - `node --check labcam/web/static/new.js`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- API smoke check passed through Flask's test client: a running
  station returned `interval_minutes` and `ended_at=None`; a finished
  station returned `interval_minutes` and a real ISO `ended_at`.
- Browser hardware validation is still pending because no live server
  was responding on `127.0.0.1:5055` during this session. No push was
  performed.

### 2026-05-28 — Phase 3.5 camera picker keyboard support added

- Added keyboard support to the custom `/new` camera picker:
  - The selected idle camera row is the tab stop.
  - Busy camera rows remain visible but are not tab-focusable.
  - `Enter` and `Space` select the focused idle camera.
  - Arrow keys move and select among idle cameras while skipping busy
    rows.
  - `Home` and `End` jump and select the first/last idle camera.
- Refined the first implementation after manual feedback: click,
  Enter/Space, arrows, Home, and End now restore focus after the
  picker re-renders, and keyboard behaviour follows the standard
  radiogroup pattern more closely.
- Added a focused-row style for `.cam:focus-visible` so keyboard focus
  is visible inside the redesigned picker.
- Preserved the hidden `camera_label` form payload, click selection,
  busy-camera lockout, name-check debounce, and Preview/Start
  validation behaviour.
- Updated `specs/phase-3.5.md` to document the keyboard interaction.
- Validation passed:
  - `node --check labcam/web/static/new.js`
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- Live browser keyboard walkthrough is still pending because no live
  server was running for this session. No push was performed.

### 2026-05-28 — Phase 3.5 design handoff folder ignored

- Added `design_handoff_lab_imaging/` to `.gitignore`. The folder may
  remain locally as a Claude Design reference export, but it is not
  tracked and is not part of the runtime dashboard.
- Updated `specs/phase-3.5.md`, `specs/05_BUILD_PLAN.md`, and
  `README.md` to describe the handoff export as local reference
  material only.
- Logged decision #17 in `DECISIONS.md`: the prototype export is
  gitignored because it can contain reference-only CDN React/Babel /
  Google Fonts links, while the actual app remains offline-capable
  Flask/Jinja/vanilla JS.
- Verified `git status --short --branch` no longer lists
  `design_handoff_lab_imaging/` as an untracked folder. No push was
  performed.

### 2026-05-28 — Phase 3.5 post-start duplicate warning suppressed

- Fixed `/new` so a successful start does not immediately show the
  duplicate-name warning for the exact camera/name that just started
  while the name remains in the input.
- The duplicate-name warning still appears when the user edits the
  name or changes cameras and the selected camera/name would create a
  suffixed folder.
- Invalidated in-flight name-check responses on successful start so an
  older duplicate check cannot repaint the warning after the success
  message.
- Preserved stale-tab and server-side busy-camera handling; this change
  only suppresses the name-warning note for the just-started
  camera/name pair.
- Updated `specs/phase-3.5.md` to document the behaviour.
- Validation passed:
  - `node --check labcam/web/static/new.js`
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- Live browser validation is still pending because no dashboard server
  was responding at `127.0.0.1:5055/new` during this session. No push
  was performed.

### 2026-05-28 — Phase 3.5 status action underline removed

- Fixed the status page "New experiment" action by adding
  `text-decoration: none` to the shared `.btn` style. This also keeps
  other anchor-backed buttons, such as `/new`'s "View status" action,
  from inheriting browser link underlines.
- Validation passed:
  - `node --check labcam/web/static/new.js`
  - `node --check labcam/web/static/status.js`
  - Confirmed the `.btn` rule now includes `text-decoration: none`.
- Live browser validation is still pending because no dashboard server
  was responding at `127.0.0.1:5055/` during this session. No push was
  performed.

### 2026-05-28 — Handoff reconciled after Phase 3.5 merge

- Verified the local checkout is clean on `main` and matches
  `origin/main`.
- Verified `main` contains merge commit `9bae6e4` from PR #4,
  `phase-3.5-ui-redesign`.
- Updated current state to show Phase 4 as the next phase to start.
- No code changes were made. No push was performed.

### 2026-05-28 — Phase 4 Windows-ready implementation

- Created branch `phase-4-windows-verification`.
- Added Windows camera enumeration in `labcam/cameras/identify_windows.py`
  using DirectShow metadata via a Windows-only `pywin32` dependency.
- Added DirectShow capture backend selection through
  `labcam/cameras/base_capture.py` and wired Windows enumeration in
  `labcam/cameras/interface.py`.
- Updated camera resolution so configured non-`index_fallback` cameras
  re-resolve by `identity_strategy` + `stable_id` under the global
  capture lock before capture.
- Added `specs/phase-4-windows-manual-validation.md` with the exact
  PowerShell commands and outputs to paste back from Windows; linked it
  from `specs/phase-4.md` and `README.md`.
- Logged decision #18 for DirectShow metadata + `pywin32`.
- Validation passed on macOS:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- Real Windows hardware validation is pending. No push was performed.

### 2026-05-29 — Phase 4 Windows metadata fallback refined

- Reviewed Windows validation output from the lab machine:
  - OpenCV 4.13.0 reports `CAP_DSHOW=700`.
  - `tools\camera_setup.py list` detected two usable OpenCV indexes but
    still fell back to `identity_strategy="index_fallback"`.
  - `Get-CimInstance Win32_PnPEntity` exposed the connected
    `Logi C310 HD WebCam` and Surface camera PnP IDs, plus many
    non-camera USB/audio/IR/controller records.
- Updated `labcam/cameras/identify_windows.py` locally to use a
  PowerShell CIM/PnP fallback when DirectShow metadata is unavailable,
  preferring actual `MI_00` video-interface camera records and filtering
  out microphone, hub, IR, controller, composite, keyboard, and mouse
  records.
- After the USB webcam was connected, setup previews showed the CIM/PnP
  metadata order was flipped relative to OpenCV indexes on this machine.
  The patch was tightened to keep CIM/PnP metadata as warning context
  only and avoid assigning wrong `hardware_id` values to OpenCV indexes.
- Validation passed on macOS:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
- Follow-up commit `a0f1b23` was pushed to
  `origin/phase-4-windows-verification`.

### 2026-05-29 — Windows Logitech setup and stress test passed

- Windows retest after pulling the safer metadata fallback:
  - `tools\camera_setup.py list` detected one usable OpenCV index at
    the time of the test: `camera-0`, `identity_strategy="index_fallback"`.
    The warning listed CIM metadata names for `Logi C310 HD WebCam` and
    `Surface Camera Front`, but did not assign unsafe hardware IDs.
  - Setup was run with `tools\camera_setup.py setup --indexes 1` after
    preview testing showed the Logitech on OpenCV index 1.
  - Generated `config\cameras.json` maps label `logi` to
    `identity_strategy="index_fallback"`, `stable_id="1"`,
    `last_seen_index=1`.
  - `tools\camera_setup.py stress-test --indexes 1 --cycles 100`
    passed 100/100 captures.
- DirectShow warnings are still emitted during index probing, but the
  target Logitech capture path succeeded.
- Dashboard smoke test with the `logi` mapping passed on Windows.
- Remaining Phase 4 identity scenarios are not fully proven because the
  current Windows setup uses `index_fallback`: reboot survival, replug
  survival, and identical-device disambiguation still need either
  stronger camera identity correlation or the final multi-camera lab
  hardware.
- No push was performed.

### 2026-05-29 — Phase 5 branch opened after Phase 4 merge

- The human merged `phase-4-windows-verification`.
- Updated local `main` from `origin/main` to merge commit `96a5838`.
- Created branch `phase-5-hardening-polish` from updated `main`.
- Updated current state to mark Phase 5 as active while preserving the
  Phase 4 identity caveat: Windows capture reliability passed for the
  Logitech C310, but durable identity remains `index_fallback` on the
  current Surface + Logitech setup.
- No code changes were made. No push was performed.

### 2026-05-29 — Phase 5 / Phase 6 scope split logged

- Reviewed `specs/post-phase4-brainstorm.md` with the human.
- Decided Phase 5 remains hardening-only: reliability, clearer error
  surfacing, lab-staff documentation, safe defaults, and final v1
  polish.
- Moved the remaining brainstorm features into a new Phase 6 holding
  spec: startup camera verification, dashboard camera configuration,
  settings, configurable save location, cloud-sync guidance,
  post-experiment notes, experiment browser, maintenance mode, and
  live-preview/repeated-preview investigation.
- Logged decisions #19 and #20 in `DECISIONS.md`.
- Updated `specs/05_BUILD_PLAN.md`, `specs/phase-5.md`,
  `specs/phase-6.md`, and `specs/post-phase4-brainstorm.md`.

### 2026-05-29 — Phase 5 task specs written

- Wrote and committed four focused Phase 5 implementation specs, one
  commit per spec:
  - `specs/phase-5-task-1-station-health.md`
  - `specs/phase-5-task-2-disk-full.md`
  - `specs/phase-5-task-3-clean-shutdown.md`
  - `specs/phase-5-task-4-lab-readme-defaults.md`
- Confirmed the docs keep Phase 5 hardening-only and defer startup
  camera verification, dashboard camera configuration, settings UI,
  experiment browser, post-experiment notes, maintenance mode, and live
  preview to Phase 6.
- No runtime code changes were made.

### 2026-05-29 — Phase 5 hardening implemented and simulated

- Implemented station health tracking in the capture engine:
  consecutive scheduled-capture failures, sanitized lab-facing health
  messages, health timestamps, and additive `/api/status` fields
  (`health_state`, `health_message`, `consecutive_failures`,
  `last_error_at`, `warnings`).
- Updated the dashboard status page to surface identity warnings,
  capture warnings/failures, unavailable cameras, and terminal storage
  problems using the existing redesigned card states and a system-alert
  banner area.
- Implemented mid-run storage failure handling. Scheduled image save,
  capture-log, metadata, or running-state write failures now stop only
  the affected experiment with `end_reason="disk_full"` or
  `end_reason="storage_failed"` when appropriate; ordinary camera
  failures still retry, log a sequence gap, and continue.
- Added clean shutdown semantics. `labcam.main` handles SIGINT/SIGTERM
  and calls `CaptureEngine.shutdown_cleanly()`, which waits for active
  capture work, finalizes running experiments as `stopped_early`, and
  clears `running_state.json`. Startup crash recovery still marks true
  stale state as `unknown`.
- Converted root `README.md` into the lab-staff runbook and moved
  developer setup, architecture notes, and validation commands into
  `CONTRIBUTING.md`.
- Reviewed `config/settings.json.example`; defaults remain unchanged:
  `allow_lan_access=false`, `jpeg_quality=90`, `capture_retries=2`,
  `default_interval_minutes=5`, `default_duration_hours=12`, and
  `warmup_frames=5`.
- Added `tools/phase5_driver.py` for deterministic simulated Phase 5
  validation.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/status.js`
  - `node --check labcam/web/static/new.js`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `.venv/bin/python tools/phase2_driver.py --profile fast
    --mock-capture --cameras station1 station2` passed 6/6 scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 12/12 scenarios.
- Real Windows hardware validation is still pending for disconnect /
  replug behavior, reboot/index-fallback preview verification, and final
  lab-machine smoke testing. Lab-staff README dry-run is also pending.
- No push was performed.

### 2026-05-29 — Phase 5 review against spec

- Reviewed current code against `HANDOFF.md`, `specs/phase-5.md`, and
  all four Phase 5 task specs.
- Re-ran deterministic validation:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/status.js`
  - `node --check labcam/web/static/new.js`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `.venv/bin/python tools/phase5_driver.py` passed 12/12 scenarios.
- No code changes were made. Findings were reported in chat.

### 2026-05-29 — Phase 5 review findings fixed

- Fixed idle configured-camera availability surfacing. The dashboard
  status path now probes idle configured cameras through the camera
  boundary and marks unavailable cameras as `camera_unavailable` /
  `offline`; `labcam.main` prints a startup warning for unavailable
  configured cameras.
- Fixed clean shutdown waiting. `shutdown_cleanly()` now waits for the
  scheduler/current capture path to finish before finalizing active
  experiments as `stopped_early`.
- Tightened storage-failure classification. Clear filesystem/storage
  failures still stop the affected experiment with `disk_full` or
  `storage_failed`; unclear JPEG-save exceptions now follow ordinary
  capture retry / sequence-gap behavior.
- Expanded `tools/phase5_driver.py` from 12 to 15 deterministic
  scenarios to cover idle unavailable cameras, unclear save failures,
  and clean shutdown waiting past the old five-second timeout.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/status.js`
  - `node --check labcam/web/static/new.js`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `.venv/bin/python tools/phase2_driver.py --profile fast
    --mock-capture --cameras station1 station2` passed 6/6 scenarios.
- Real Windows hardware validation is still pending for disconnect /
  replug behavior, reboot/index-fallback preview verification, and final
  lab-machine smoke testing. Lab-staff README dry-run is also pending.
- No push was performed.

### 2026-05-31 — Phase 6 task specs written

- Created and switched to branch `phase-6-dashboard-workflows` from the
  completed Phase 5 branch.
- Wrote nine Phase 6 implementation-spec docs:
  - `specs/phase-6-task-1-startup-camera-verification.md`
  - `specs/phase-6-task-2-dashboard-camera-configuration.md`
  - `specs/phase-6-task-3-settings-page.md`
  - `specs/phase-6-task-4-configurable-save-location.md`
  - `specs/phase-6-task-5-cloud-sync-guidance.md`
  - `specs/phase-6-task-6-post-experiment-notes.md`
  - `specs/phase-6-task-7-experiment-browser.md`
  - `specs/phase-6-task-8-maintenance-mode.md`
  - `specs/phase-6-task-9-preview-investigation.md`
- Updated `specs/phase-6.md` to link each task spec and preserve the
  intended one-task-at-a-time sequence.
- Logged decisions #21 and #22 in `DECISIONS.md` for the Phase 6 task
  split and the `post_notes.txt` storage choice.
- No runtime code changes were made. No push was performed.

### 2026-05-31 — Phase 6 Task 1 startup verification implemented

- Implemented the startup camera verification gate. `/` and `/new`
  redirect to `/verify-cameras` until every configured station has been
  confirmed in the current app process, and experiment start requests
  are blocked until confirmation is complete.
- Added the verification dashboard page and API:
  `/api/verification`, `/api/verification/confirm`, and the existing
  preview endpoint for fresh still previews.
- Confirmation uses the existing preview capture path under the
  process-wide capture lock, preserves open-grab-close camera behavior,
  and writes `last_confirmed_at` plus `last_confirmed_index` to
  `config/cameras.json` without changing the required camera fields.
- Weak identity mappings are surfaced in the verification status and UI;
  failed preview captures cannot confirm a station.
- Updated `tools/phase5_driver.py` so existing simulated Phase 5
  scenarios perform startup confirmation before starting mock
  experiments under the new gate.
- Added `tools/phase6_task1_driver.py` covering startup redirects,
  strong identity confirmation, index-fallback warnings, unavailable
  cameras, persisted confirmation metadata, and process-restart session
  reset.
- Logged decision #23 in `DECISIONS.md`: confirmation is session-scoped,
  while persisted metadata is only evidence of the last confirmed
  mapping.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/verify.js`
  - `node --check labcam/web/static/new.js`
  - `node --check labcam/web/static/status.js`
  - `.venv/bin/python tools/phase6_task1_driver.py` passed 5/5
    scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- Browser plugin tooling was unavailable in this session and Playwright
  was not installed, so UI verification was limited to Flask-rendered
  page/API checks plus JavaScript syntax checks. No push was performed.

### 2026-05-31 — Phase 6 Task 2 dashboard camera configuration implemented

- Added the dashboard Cameras page at `/cameras` with detected-camera
  listing, fresh still preview controls, station-label assignment,
  optional notes, clear `index_fallback` warnings, and a sequential
  stress-test panel.
- Added camera configuration APIs:
  `/api/cameras/detected`, `/api/cameras/detected/preview`,
  `/api/cameras/config`, and `/api/cameras/stress-test`.
- Added engine support for detected-camera listing, detected-camera
  preview, atomic `config/cameras.json` writes using the existing schema,
  dashboard stress-test reports, and process-session verification reset
  after saving a new mapping.
- Adjusted dashboard startup so a missing `config/cameras.json` no
  longer prevents app startup; `/` and `/new` route to `/cameras` until
  camera mapping is saved. `tools/camera_setup.py` remains unchanged as
  a developer fallback.
- Added `tools/phase6_task2_driver.py` covering detection, assignment
  save compatibility, fallback warnings, stress-test success,
  stress-test failure reporting, and verification reset after save.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/cameras.js`
  - `.venv/bin/python tools/phase6_task2_driver.py` passed 6/6
    scenarios.
  - `.venv/bin/python tools/phase6_task1_driver.py` passed 5/5
    scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
- Browser smoke verification used a temporary mocked Flask server because
  the Codex app process still lacks macOS camera permission. `/cameras`
  rendered detected cameras, preview capture displayed a still image,
  and the stress-test panel reported both mocked cameras as 100/100
  passed.
- No push was performed.

### 2026-05-31 — Phase 6 Task 2 hot-plug detection follow-up implemented

- Confirmed the user-reported bug: if the dashboard started before the
  USB webcam was plugged in, `/cameras` detection stayed stale, while a
  fresh `.venv/bin/python tools/camera_setup.py list` process detected
  the USB webcam and a dashboard restart then detected it too.
- Added `labcam/cameras/probe.py`, a fresh-process JSON camera probe
  used by dashboard detection.
- Updated the dashboard detection path to default to the fresh-process
  camera probe while leaving configured-camera preview, stress test, and
  experiment capture on the existing capture path.
- Added a setup guard so dashboard detection, detected-camera preview,
  camera config save, and dashboard stress test return busy while an
  experiment is starting, capturing, or running.
- Extended `tools/phase6_task2_driver.py` with fresh-process detector
  and active-experiment busy-guard scenarios.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/cameras.js`
  - `.venv/bin/python tools/phase6_task2_driver.py` passed 8/8
    scenarios.
  - `.venv/bin/python tools/phase6_task1_driver.py` passed 5/5
    scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
- Manual real-camera hot-plug validation still needs to be run from the
  approved Terminal-hosted dashboard because the Codex app process lacks
  macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 2 hot-plug preview follow-up implemented

- User validation showed fresh-process dashboard detection now sees a
  USB webcam plugged in after dashboard startup, but detected-camera
  preview still failed for the hot-plugged webcam while laptop-camera
  preview worked.
- Extended `labcam/cameras/probe.py` with a fresh-process preview mode
  that captures and writes a JPEG for a detected OpenCV index.
- Added `preview_camera_fresh_process()` in `labcam/cameras/interface.py`
  and routed `CaptureEngine.preview_detected_camera()` through it.
- Left configured-camera preview, scheduled capture, and dashboard
  stress test on the existing capture path. This follow-up only changes
  the `/cameras` detected-camera preview path.
- Extended `tools/phase6_task2_driver.py` so the fresh-process scenario
  verifies both detection and detected-camera preview.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/cameras.js`
  - `.venv/bin/python tools/phase6_task2_driver.py` passed 8/8
    scenarios.
  - `.venv/bin/python tools/phase6_task1_driver.py` passed 5/5
    scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
- Manual real-camera hot-plug preview validation still needs to be run
  from the approved Terminal-hosted dashboard because the Codex app
  process lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 2 stale camera preview guard implemented

- User validation found that unplugging the USB webcam without clicking
  Detect left stale `/cameras` rows on screen. Previewing the old webcam
  row could capture the laptop camera after OpenCV reused indexes, and
  re-detecting after replug could show a stale previous preview.
- Updated `/cameras` JavaScript so Detect clears all preview object
  URLs, stress-test results, and setup alerts before fetching new
  camera results.
- Preview, Save mapping, and Stress test now refresh the detected camera
  list before acting. If the list changed, the UI re-renders, clears
  preview state, and warns: "Camera list changed. Capture preview again
  before saving or testing cameras."
- Preview state is keyed by the current detected camera signature and
  detection revision instead of only by OpenCV index.
- Save mapping is disabled and server submission is blocked until every
  currently detected camera has a fresh preview captured after the
  latest Detect.
- The detected-preview API now reports a clearer changed-list message
  when the helper process says a requested camera index is no longer
  detected.
- Extended `tools/phase6_task2_driver.py` with a stale-preview error
  scenario; it now covers fresh-process detection/preview, setup save,
  fallback warnings, stress success/failure, stale preview errors,
  verification reset, and active-experiment blocking.
- Browser smoke validation used a temporary mocked Flask server and
  dynamic detected-camera list. It verified:
  - Two detected cards initially render with Save disabled.
  - After one preview, Save remains disabled until all current cameras
    have fresh previews.
  - When the mocked list changes from two cameras to one, clicking
    preview on the stale row re-renders to one card, clears old previews,
    shows the changed-list warning, and keeps Save disabled.
  - After re-detecting two cameras, no old preview image appears.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/cameras.js`
  - `.venv/bin/python tools/phase6_task2_driver.py` passed 9/9
    scenarios.
  - `.venv/bin/python tools/phase6_task1_driver.py` passed 5/5
    scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
- Manual real-camera stale-row/hot-plug preview validation still needs
  to be run from the approved Terminal-hosted dashboard because the
  Codex app process lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 2 draft mapping inputs preserved

- User validation found that clicking Capture preview on `/cameras`
  rebuilt the camera cards and reset unsaved station labels/notes to
  the last saved mapping values.
- Added page-local draft mapping state to `labcam/web/static/cameras.js`
  for station label, notes, and stress-test selection, keyed by the
  current detected camera signature.
- Same-camera-list re-renders now snapshot draft inputs before
  rebuilding cards, so Capture preview start/finish/failure and
  same-list detection refreshes preserve unsaved text until Save mapping
  is clicked.
- Explicit Detect and changed camera-list refreshes still clear draft
  values, because index reuse may mean the old text now refers to the
  wrong physical camera.
- Save mapping success clears the draft state and re-renders from the
  saved server response so the UI matches persisted config.
- Added `tools/phase6_task2_browser_smoke.js`, a dependency-free JS DOM
  harness for the `/cameras` script. It verifies draft labels/notes
  survive preview re-renders, survive previewing another camera, preserve
  stress checkbox edits, and clear when the detected camera list changes.
- Validation passed:
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/cameras.js`
  - `node --check tools/phase6_task2_browser_smoke.js`
  - `node tools/phase6_task2_browser_smoke.js`
  - `.venv/bin/python tools/phase6_task2_driver.py` passed 9/9
    scenarios.
  - `.venv/bin/python tools/phase6_task1_driver.py` passed 5/5
    scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
- Manual real-camera draft-input validation still needs to be run from
  the approved Terminal-hosted dashboard because the Codex app process
  lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 3 settings page implemented

- Added `/settings` and dashboard navigation for safe system settings.
- Added `GET /api/settings` and `POST /api/settings`; settings are
  merged with `config/settings.json.example` defaults, missing
  `settings.json` is created from defaults, saves are atomic, and only
  the safe v1 capture defaults are editable.
- Editable settings are default interval minutes, default duration
  hours, JPEG quality, capture retries, and warmup frames.
- Settings saves are blocked with `settings_busy` while any experiment
  is starting or running so active capture behavior cannot change
  mid-run.
- The Settings page shows read-only diagnostics: experiments directory,
  settings path, camera config path, LAN access state, Python version,
  OpenCV version, and git commit when available.
- Exposed OpenCV version through `labcam/cameras/` so no code outside
  the camera package imports OpenCV.
- Added `tools/phase6_task3_driver.py` covering page render, defaults
  merge, valid saves, invalid rejection, missing settings creation, and
  active-experiment save blocking.
- Appended Decision 24 documenting the active-run settings-save block.
- Validation passed:
  - `.venv/bin/python tools/phase6_task3_driver.py` passed 6/6
    scenarios.
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/settings.js`
  - `node --check labcam/web/static/new.js`
  - `node --check labcam/web/static/cameras.js`
  - `node --check labcam/web/static/status.js`
  - `.venv/bin/python tools/phase6_task2_driver.py` passed 9/9
    scenarios.
  - `.venv/bin/python tools/phase6_task1_driver.py` passed 5/5
    scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `node --check tools/phase6_task2_browser_smoke.js`
  - `node tools/phase6_task2_browser_smoke.js`
  - `git diff --check`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
- Manual real-camera stale-row/hot-plug preview and draft-input
  validation remains pending from Task 2 because the Codex app process
  lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Download and run question answered

- No code changes this session.
- Reviewed the current handoff, Phase 6 spec, README, CONTRIBUTING
  setup notes, requirements, settings example, and git branch state to
  explain how another person can download and run the software today.

### 2026-05-31 — Phase 6 Task 4 configurable save location implemented

- Added editable `experiments_dir` storage controls to the Settings page.
  The dashboard validates that the configured folder exists or can be
  created, rejects file/non-directory paths, verifies write access with a
  temporary file, and saves the operator-entered path to
  `config/settings.json`.
- Settings saves now allow save-location-only changes during active
  experiments while keeping capture defaults locked until active runs
  stop.
- `CaptureEngine.reload_settings()` refreshes the future
  `experiments_dir` for dashboard/app engines while preserving explicit
  test/tool overrides. Active experiments keep writing through their
  existing `Experiment.paths`.
- New `running_state.json` entries include `experiment_folder`; startup
  recovery prefers that stored folder and falls back to the old
  `experiments_dir / experiment_id` lookup for compatibility.
- Updated the README storage/backups wording and appended Decisions 25
  and 26 for active-run save-location changes and stored experiment
  folders in runtime state.
- Added `tools/phase6_task4_driver.py` covering absolute and relative
  paths, missing-folder creation, invalid/unwritable paths, active-run
  old-folder preservation plus future-run new-folder use, restart
  persistence, and startup recovery from an old folder.
- Validation passed:
  - `.venv/bin/python tools/phase6_task4_driver.py` passed 7/7
    scenarios.
  - `.venv/bin/python tools/phase6_task3_driver.py` passed 6/6
    scenarios.
  - `.venv/bin/python tools/phase6_task2_driver.py` passed 9/9
    scenarios.
  - `.venv/bin/python tools/phase6_task1_driver.py` passed 5/5
    scenarios.
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/settings.js`
  - `node --check labcam/web/static/new.js`
  - `node --check labcam/web/static/cameras.js`
  - `node --check labcam/web/static/status.js`
  - `node --check tools/phase6_task2_browser_smoke.js`
  - `node tools/phase6_task2_browser_smoke.js`
  - `git diff --check`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
- Manual real-camera stale-row/hot-plug preview and draft-input
  validation remains pending from Task 2 because the Codex app process
  lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 5 cloud sync guidance implemented

- Expanded the README Cloud Sync and Backups section with the supported
  local-sync pattern: choose a normal local folder managed by OneDrive,
  Google Drive Desktop, Dropbox, Synology Drive, or a network sync tool;
  Lab Imaging writes local files first; existing sync software copies
  files after they are written; experiments continue without internet.
- Added a persistent Settings / Storage info note next to the
  `experiments_dir` control. The note keeps cloud backup guidance
  conservative and explicitly warns against browser uploads or
  internet-dependent transfers during active capture.
- Added `tools/phase6_task5_driver.py` to verify the Settings guidance,
  README guidance, and absence of cloud/client dependencies in
  `requirements.txt`.
- No capture logic, settings schema, API, cloud credential handling,
  sync status tracking, upload worker, or internet dependency was added.
- Validation passed:
  - `.venv/bin/python tools/phase6_task5_driver.py` passed 3/3
    scenarios.
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/settings.js`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg -n "onedrive|google.*drive|dropbox|synology|s3|ftp|oauth|token|upload worker|sync status" requirements.txt labcam tools README.md specs/phase-6-task-5-cloud-sync-guidance.md`
    found only expected documentation/driver references plus existing
    unrelated `token` variable names in `tools/phase2_driver.py`.
  - Case-insensitive cloud-keyword grep confirmed the README and
    Settings page contain the intended guidance.
- Manual real-camera stale-row/hot-plug preview and draft-input
  validation remains pending from Task 2 because the Codex app process
  lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 6 post-experiment notes implemented

- Implemented post-run notes as `post_notes.txt` sidecar files inside
  finalized experiment folders. Non-empty saves are atomic; blank or
  whitespace-only saves delete the sidecar file.
- Added the dashboard note editor at
  `/experiments/<experiment_id>/notes` plus JSON APIs:
  `GET /api/experiments/<experiment_id>/post-notes` and
  `POST /api/experiments/<experiment_id>/post-notes`.
- Notes are rejected for active or unfinished experiments. Original
  start-time `metadata.json` notes remain unchanged.
- Terminal station status payloads now include `has_post_notes` and
  `post_notes_url`, and finished/stopped/failed station cards show
  Add/Edit notes links. Task 7's full experiment browser was not
  implemented.
- Updated `specs/phase-6.md` so Suggested Ordering matches the current
  Task 6 before Task 7 sequence. Updated
  `specs/phase-6-task-6-post-experiment-notes.md` and appended
  Decision 27 for blank-note deletion.
- Added `tools/phase6_task6_driver.py` covering add/edit/delete,
  metadata preservation, active-run rejection, status-card links, the
  notes page, and invalid/traversal id rejection.
- Validation passed:
  - `.venv/bin/python tools/phase6_task6_driver.py` passed 7/7
    scenarios.
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/status.js`
  - `node --check labcam/web/static/experiment_notes.js`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- Manual real-camera stale-row/hot-plug preview and draft-input
  validation remains pending from Task 2 because the Codex app process
  lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 7 experiment browser implemented

- Added the read-only dashboard experiment browser:
  `/experiments`, `/experiments/<experiment_id>`,
  `GET /api/experiments`, and
  `GET /api/experiments/<experiment_id>`.
- The browser scans the configured `experiments_dir` directly. It lists
  immediate experiment folders, filters by date and station, shows
  status/end reason, image count, folder path, metadata, capture-log
  summary, post-run notes, and the latest still only.
- Missing or malformed `metadata.json` folders are shown as incomplete
  with warnings instead of crashing the page.
- `GET /api/experiments/<experiment_id>/latest` still serves active
  in-memory experiment frames and now falls back to the latest
  `images/*.jpg` for historical folders.
- Added `tools/phase6_task7_driver.py` covering list, filters, detail,
  latest stills, malformed folders, large image counts, read-only route
  behavior, and invalid/traversal id rejection.
- In-app browser smoke validation passed on a temporary dashboard server
  at `http://127.0.0.1:5057`: `/experiments` rendered local experiment
  folders, and a detail page rendered the latest still and log summary.
- Validation passed:
  - `.venv/bin/python tools/phase6_task7_driver.py` passed 6/6
    scenarios.
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/experiments.js`
  - `node --check labcam/web/static/experiment_detail.js`
  - `.venv/bin/python tools/phase6_task6_driver.py` passed 7/7
    scenarios.
  - `git diff --check`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
  - `rg "platform\\.system|sys\\.platform|os\\.name" -n labcam tools`
    reports only `labcam/cameras/interface.py`.
- Manual real-camera stale-row/hot-plug preview and draft-input
  validation remains pending from Task 2 because the Codex app process
  lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 8 maintenance mode implemented

- Implemented maintenance mode for active experiments on branch
  `phase-6-dashboard-workflows`.
- Added `CaptureEngine.enter_maintenance()` and
  `CaptureEngine.resume_maintenance()`. Maintenance keeps the
  experiment active, pauses scheduled captures, lets other stations keep
  capturing, and supports stop-early finalization while paused.
- Recorded the Phase 6 Task 8 sequence policy in `DECISIONS.md`:
  intentional maintenance skips do not create image sequence gaps.
  Instead, each window records start/end/note and skipped capture count
  in `metadata.json` and `capture_log.txt`.
- Added maintenance fields to active status and `running_state.json`;
  startup recovery remains Option A and still finalizes stale running
  entries as `unknown`.
- Added dashboard API routes:
  `POST /api/experiments/<id>/maintenance/start` and
  `POST /api/experiments/<id>/maintenance/resume`.
- Updated the station status page to show a distinct Maintenance state,
  maintenance notes, skipped capture count, Resume, and Stop controls.
  No live preview or repeated preview behavior was added.
- Added `tools/phase6_task8_driver.py` with six deterministic scenarios.
- Validation passed:
  - `.venv/bin/python tools/phase6_task8_driver.py` passed 6/6
    scenarios.
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/status.js`
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `.venv/bin/python tools/phase6_task6_driver.py` passed 7/7
    scenarios.
  - `.venv/bin/python tools/phase6_task7_driver.py` passed 6/6
    scenarios.
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- Manual real-camera stale-row/hot-plug preview and draft-input
  validation remains pending from Task 2 because the Codex app process
  lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 8 maintenance preview follow-up implemented

- Added a maintenance-only `Capture preview` action on the station
  status card. It calls the existing `POST /api/preview` fresh-still
  route and displays the returned still in the maintenance station
  frame.
- Preview remains open-grab-close and still routes through the existing
  capture lock. No streaming endpoint, polling preview loop, camera
  manager, or live-preview behavior was added.
- Maintenance previews are temporary UI previews only. They are not
  written into the experiment `images/` folder, do not advance image
  sequence numbers, and do not change `metadata.json` image counts or
  maintenance skipped counts.
- Preview controls remain absent from ordinary running station cards;
  operators can preview only while a station is in maintenance.
- Failed maintenance previews show an inline dashboard error while the
  experiment remains in maintenance mode.
- Extended `tools/phase6_task8_driver.py` with maintenance preview
  coverage. It now passes 9/9 deterministic scenarios.
- Validation passed:
  - `.venv/bin/python tools/phase6_task8_driver.py` passed 9/9
    scenarios.
  - `.venv/bin/python -m compileall labcam tools`
  - `node --check labcam/web/static/status.js`
  - `.venv/bin/python tools/phase5_driver.py` passed 15/15 scenarios.
  - `.venv/bin/python tools/phase6_task6_driver.py` passed 7/7
    scenarios.
  - `.venv/bin/python tools/phase6_task7_driver.py` passed 6/6
    scenarios.
  - `git diff --check`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- Manual real-camera stale-row/hot-plug preview and draft-input
  validation remains pending from Task 2 because the Codex app process
  lacks macOS camera permission.
- No push was performed.

### 2026-05-31 — Phase 6 Task 9 preview recommendation completed

- Completed Phase 6 Task 9 as a docs-only investigation outcome.
- Updated `specs/phase-6-task-9-preview-investigation.md` into the
  final recommendation report.
- Recommended keeping production preview as repeated fresh stills for
  the current Phase 6 completion path.
- Explicitly rejected continuous live preview, streaming endpoints, and
  long-lived camera managers unless a later implementation spec changes
  the preview model and includes Windows hardware validation.
- Added the repeated-still UX improvement rules: `/api/preview` remains
  open-grab-close, future auto-refresh must be bounded and active-view
  scoped, busy cameras must show explicit feedback, and preview refresh
  must not affect experiment images, sequence numbers, or metadata
  image counts.
- Logged decision #29 in `DECISIONS.md`.
- Validation passed:
  - `git diff --check`
  - `rg "import cv2|from cv2" -n labcam tools` reports only
    `labcam/cameras/base_capture.py`.
  - `rg "cv2\\.imshow" -n labcam tools` reports no matches.
  - `rg "^opencv-python($|[<=>])" -n requirements.txt` reports no
    matches.
- No production preview code, streaming route, camera manager, or
  frontend live-preview UI was added.
- No push was performed.
