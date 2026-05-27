# HANDOFF.md — Live Project Status

State only. No rules. Rules live in `AGENTS.md`.

Every session updates this file as its last action, even if nothing
changed (write "no changes this session" explicitly under that date).

---

## Current state

- **Current phase:** Phase 3 — local Flask dashboard implemented,
  review notes fixed, and validated on the Mac dev machine; ready for
  review.
- **Current branch:** `phase-3-dashboard`.
- **Open questions:** none.
- **Known issues:** macOS AVFoundation also exposes a Continuity/iPhone
  camera at index 2; it is excluded from the current lab camera mapping.
  The Codex app process still lacks macOS camera permission, but the
  approved Terminal can run the real-camera driver successfully.
- **Next actions:** Review/merge Phase 3 dashboard branch.

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
