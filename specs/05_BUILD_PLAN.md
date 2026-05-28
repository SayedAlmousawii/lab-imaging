# Build Plan & Roadmap

The build order is deliberate: prove the hardware works first, then the headless
engine, then the UI on top. Each phase produces something testable on its own.

## Phase 0 — Project Setup
- Create the package structure (see `03_PROJECT_STRUCTURE.md`).
- `requirements.txt`: `opencv-python-headless`, web framework (Flask or FastAPI),
  and any small OS-helper deps for camera identification.
- `README.md` with install + run steps.
- Confirm Python 3.11 runs and OpenCV imports on the **Mac dev machine**
  (M3, macOS 26.4.1).

## Phase 1 — Camera Test & Labeling Tool  ← build first
Goal: prove the actual webcams work and establish camera labels plus identity
strategy metadata.
- `tools/camera_setup.py`:
  - Enumerate available cameras.
  - Save a button-triggered fresh preview snapshot for each camera to the OS temp
    directory (`tempfile.gettempdir()`), then print the absolute path. Do not
    write previews into `experiments/`. Do not use `cv2.imshow`.
  - Let the user assign a free-form sanitized label (`station1` suggested) and
    optional notes to each camera.
  - Record `identity_strategy`, `stable_id`, `last_seen_index`, and `warnings`
    for each camera.
  - Save `config/cameras.json`.
- Implement `cameras/interface.py` + `cameras/base_capture.py` (open-grab-close)
  + the macOS identification path.
- `tools/camera_setup.py` must use only `labcam/cameras/` APIs and must not
  import `cv2` directly.
- Test on the available Mac hardware: built-in Mac camera + at least one Logitech
  C310 USB webcam.
- Run a repeated open-grab-close stress test before unplug/replug testing:
  100 capture cycles per camera.
- Identical-device validation is deferred to Phase 4 Windows verification,
  because a second identical webcam is not available on the Mac dev machine.
- **Deliverable:** you can list, preview, and label your Mac's camera(s) and the
  mapping persists.

## Phase 2 — Capture Engine (headless)
Goal: reliable scheduled capture with no UI.
- `engine/experiment.py` — experiment model + lifecycle (start, tick, finalize).
- `engine/storage.py` — folder creation, timestamped filenames, `metadata.json`,
  `capture_log.txt`.
- `engine/scheduler.py` — the loop: find due experiments, **staggered**
  open-grab-close captures (never two cameras open at once, enforced by one
  process-wide global capture lock), write images, finalize on duration elapse,
  log everything. One failed scheduled capture → log + retry (per
  `capture_retries`) → record a sequence gap if all retries fail → continue;
  never kill an already-running experiment.
- `engine/state.py` — running-state file.
- Enforce one active experiment per camera/station.
- Capture **t=0 baseline** immediately on start. If the baseline capture fails
  after retries, fail the experiment start.
- Check available disk space at experiment start and fail early if clearly
  insufficient.
- **Deliverable:** start an experiment from a script (e.g. 2-min duration, 20-sec
  interval for testing), get a complete folder with correctly-named images,
  metadata, and a log. Run 2+ concurrent experiments and confirm staggering.

## Phase 3 — Local Web Dashboard
Goal: control + monitor without touching code.
- `web/server.py` — local HTTP server + routes (list cameras, preview snapshot,
  create/start experiment, stop experiment, status of all stations, latest frame).
- `templates/` + `static/` — two screens:
  - **Status view:** table of stations/experiments — label, status, and for
    running ones: name, elapsed, images captured, time remaining.
  - **New-experiment panel:** camera dropdown (labels), name, interval, duration,
    operator/notes, **Preview** (fresh snapshot), **Start**.
  - Per running experiment: **Stop** + view latest captured frame.
- `main.py` — start engine + server together; one command.
- **Deliverable:** full workflow through the browser on the Mac.

## Phase 3.5 — Dashboard UI Polish / Redesign
Goal: ship the Claude Design redesign of the Phase 3 dashboard without
changing backend behaviour. See `specs/phase-3.5.md` for the
authoritative spec.
- Replace `labcam/web/static/styles.css` with the design-system
  stylesheet; self-host Inter + JetBrains Mono under
  `labcam/web/static/fonts/` (SIL OFL 1.1).
- Rewrite `templates/base.html`, `templates/status.html`,
  `templates/new.html`, `static/status.js`, `static/new.js` to the
  new markup (topbar + summary strip + station card grid; config-grid
  with cam-picker, input-group, run-summary, and preview aside).
- All Flask routes, polling cadence (10 s status / 3 s thumbnail),
  debounce, and validation rules unchanged. Engine code untouched.
  Existing JSON payloads may gain additive display-only fields.
- **Deliverable:** the four Phase 3 functional tests still pass
  against the redesigned UI, plus visual parity with the local design
  reference when available. The `design_handoff_lab_imaging/` export is
  gitignored reference material, not shipped runtime code.

## Phase 4 — Windows Verification  ← mandatory before go-live
Goal: confirm on the real target.
- Implement/verify `cameras/identify_windows.py` (DirectShow, identity strategy
  metadata).
- Run on an actual **Windows lab machine** with the **actual webcams** and a
  **powered USB hub**.
- Test: 4 concurrent cameras; labels and identity matching survive a
  reboot/replug when the identity strategy supports it; identical Logitech C310
  units; a real multi-hour run; framing/preview correctness; staggered captures
  under load.
- Fix any quirks **inside `cameras/` only** — nothing above it should change.
- **Deliverable:** a documented, repeatable run on Windows.

## Phase 5 — Hardening & Polish
- Graceful handling of: camera disconnect mid-run, disk full, app shutdown.
- Clear error surfacing in the dashboard (e.g. "Station 2 capture failing").
- README finalized for lab staff (plain-language run instructions).
- Sensible defaults in `settings.json`.

## Out of Scope for v1 (Future Extensions)
Documented so they're not accidentally built now, but designed-around:
- **Auto-resume after crash/reboot** (Option B) — engine could detect an
  experiment still within its planned window and continue for the remaining time.
- **Automatic level detection** (computer vision reading the ruler) — the manual
  reading workflow produces the labeled image corpus this would later train/test on.
- **Multi-PC scaling** — a second Windows machine running the same software for
  more stations; optionally a combined status view.
- **Event-based triggers** (motion/color change) instead of fixed interval.
- **Remote/LAN dashboard access** hardening (auth) if used beyond localhost.

## Testing Notes
- For fast iteration, test with **short durations and short intervals**
  (e.g. 2-minute duration, 20-second interval) — same code paths, quick feedback.
- Verify filenames sort correctly and timestamps match capture times.
- Verify concurrent experiments never open two cameras at the same instant.
- Verify an induced capture failure logs an error and the run continues.
