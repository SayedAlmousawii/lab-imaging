# HANDOFF.md — Live Project Status

State only. No rules. Rules live in `AGENTS.md`.

Every session updates this file as its last action, even if nothing
changed (write "no changes this session" explicitly under that date).

---

## Current state

- **Current phase:** Phase 2 — capture engine implemented and validated;
  ready for review/merge. Phase 3 can begin after Phase 2 lands.
- **Current branch:** `phase-2-capture-engine`.
- **Open questions:** none.
- **Known issues:** macOS AVFoundation also exposes a Continuity/iPhone
  camera at index 2; it is excluded from the current lab camera mapping.
  The Codex app process still lacks macOS camera permission, but the
  approved Terminal can run the real-camera driver successfully.
- **Next actions:** Review/merge Phase 2. After Phase 2 lands, begin
  Phase 3 on a new branch from updated `main`.

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
