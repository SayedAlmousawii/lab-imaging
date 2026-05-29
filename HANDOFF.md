# HANDOFF.md — Live Project Status

State only. No rules. Rules live in `AGENTS.md`.

Every session updates this file as its last action, even if nothing
changed (write "no changes this session" explicitly under that date).

---

## Current state

- **Current phase:** Phase 5 — hardening and polish implementation is
  complete on macOS with deterministic simulated validation. Real
  Windows hardware validation and a lab-staff README dry-run are still
  required before marking v1 complete.
- **Current branch:** `phase-5-hardening-polish`.
- **Open questions:** none.
- **Known issues:** macOS AVFoundation also exposes a Continuity/iPhone
  camera at index 2; it is excluded from the current lab camera mapping.
  The Codex app process still lacks macOS camera permission, but the
  approved Terminal can run the real-camera driver successfully.
- **Next actions:** Run the remaining Phase 5 go-live checks on the
  Windows lab machine: camera disconnect/replug during a run, reboot /
  index-fallback preview verification, dashboard smoke test, and a
  cold lab-staff README read-through. Post-Phase-4 usability features
  remain deferred to Phase 6.

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
