# HANDOFF.md — Live Project Status

State only. No rules. Rules live in `AGENTS.md`.

Every session updates this file as its last action, even if nothing
changed (write "no changes this session" explicitly under that date).

---

## Current state

- **Current phase:** Phase 1 — camera test & labeling tool. Code
  implemented; target Mac hardware validated for camera indexes 0 and 1.
- **Current branch:** `phase-1-camera-setup`.
- **Open questions:** none.
- **Known issues:** macOS AVFoundation also exposes a Continuity/iPhone
  camera at index 2; it could capture a preview once but failed the
  100-cycle stress test at cycle 1. It is not included in the current
  lab camera mapping.
- **Next actions:** perform unplug/replug re-enumeration testing for the
  Logitech C310 and built-in camera on this Mac. If the mapping changes,
  rerun `python tools/camera_setup.py setup --indexes 0 1` from an
  approved Terminal. Phase 4 must still do real Windows hardware
  identity validation.

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
