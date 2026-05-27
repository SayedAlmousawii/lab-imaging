# Phase 0 — Project Setup

This is the authoritative spec for Phase 0 work. It consolidates the Phase 0
section of `05_BUILD_PLAN.md` with the directory layout from
`03_PROJECT_STRUCTURE.md` and the settings schema from `04_DATA_FORMATS.md`.
If anything in the broader specs contradicts this file for Phase 0 scope,
this file wins for Phase 0.

## Goal

Stand up the empty Python package structure, dependency manifest, and
example config so Phase 1 has somewhere to put code. No application logic
yet — just the skeleton and a one-time sanity check that the dev toolchain
actually works on this machine.

## Deliverables

1. **Package skeleton** exactly as laid out in `03_PROJECT_STRUCTURE.md`:
   ```
   labcam/
     __init__.py
     cameras/__init__.py
     engine/__init__.py
     web/__init__.py
     web/static/   (empty, .gitkeep)
     web/templates/   (empty, .gitkeep)
   tools/
     (empty until Phase 1; no __init__.py — `tools/` is not a package)
   config/
     settings.json.example
   ```
   `__init__.py` files are empty placeholders. No real code lands in Phase 0.

2. **`requirements.txt`** at the project root pinning:
   - `opencv-python-headless` (not `opencv-python`).
   - The chosen web framework — left to Phase 3 to pin, **omit from Phase 0
     requirements** so we don't drag in a dependency we haven't committed to
     yet.
   - Any small OS-helper deps needed for camera identification (Phase 1
     will decide and add; Phase 0 leaves them out).

   Phase 0 requirements is intentionally minimal: just
   `opencv-python-headless` for now.

3. **`config/settings.json.example`** — tracked in git, copied to
   `config/settings.json` on first run (which is gitignored). Schema per
   `04_DATA_FORMATS.md`:
   ```json
   {
     "experiments_dir": "./experiments",
     "web_port": 5000,
     "allow_lan_access": false,
     "warmup_frames": 5,
     "capture_retries": 2,
     "default_interval_minutes": 5,
     "default_duration_hours": 12,
     "jpeg_quality": 90
   }
   ```

4. **`README.md`** at the project root — a short developer-facing setup
   guide:
   - Python 3.11 prerequisite.
   - `python -m venv .venv && source .venv/bin/activate`.
   - `pip install -r requirements.txt`.
   - "See `AGENTS.md` and `specs/` for the design. Start with
     `specs/00_README.md`."
   - Mention that this is not the lab-staff README; that lives elsewhere
     and is finalized in Phase 5.

5. **Toolchain sanity check** (one-time, manual):
   - Create the venv, install requirements.
   - `python -c "import cv2; print(cv2.__version__)"` runs cleanly on the
     Mac dev machine (M3, macOS 26.4.1).
   - Document the version observed in the next `HANDOFF.md` update.

## Constraints

- **No code.** `__init__.py` files are empty. No imports, no logic.
- **`config/settings.json.example` is the only tracked config file.** The
  live `config/settings.json`, `config/cameras.json`, and
  `config/running_state.json` are all gitignored and created at runtime.
- **`README.md` does not duplicate `specs/`.** It points at the specs and
  covers only setup mechanics.

## Out of scope for Phase 0

- Camera enumeration code — Phase 1.
- The capture engine — Phase 2.
- The web dashboard and its framework choice — Phase 3.
- Windows-specific code — Phase 4.

## Definition of done

- The directory tree above exists with the listed files, all empty
  placeholders except `requirements.txt`, `settings.json.example`, and
  `README.md`.
- `pip install -r requirements.txt` succeeds inside a fresh venv on the
  Mac dev machine.
- `import cv2` works in that venv.
- `git status` is clean on the Phase 1 branch with the new files
  committed.
- `HANDOFF.md` updated with the observed OpenCV version and current
  state ("Phase 0 complete; Phase 1 in progress").
