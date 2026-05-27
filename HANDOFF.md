# HANDOFF.md — Live Project Status

State only. No rules. Rules live in `AGENTS.md`.

Every session updates this file as its last action, even if nothing
changed (write "no changes this session" explicitly under that date).

---

## Current state

- **Current phase:** Phase 1 — camera test & labeling tool. Not yet
  started.
- **Current branch:** `phase-1-camera-setup`.
- **Open questions:** none.
- **Known issues:** none.
- **Next actions:** in the next session, implement the Phase 0 skeleton
  (package directories, `requirements.txt`, `README.md`,
  `config/settings.json.example`), then the Phase 1 deliverables per
  `specs/phase-1.md` (`labcam/cameras/interface.py`,
  `labcam/cameras/base_capture.py`, `labcam/cameras/identify_macos.py`,
  and `tools/camera_setup.py`).

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
