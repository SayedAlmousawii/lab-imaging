# Phase 2 — Capture Engine (headless)

This is the authoritative spec for Phase 2 work. It consolidates the
Phase 2 section of `05_BUILD_PLAN.md` with the engine module
responsibilities from `03_PROJECT_STRUCTURE.md` and the on-disk formats
from `04_DATA_FORMATS.md`. If anything in the broader specs contradicts
this file for Phase 2 scope, this file wins for Phase 2.

## Goal

Build a fully working headless capture engine — no UI. After Phase 2, a
short Python script can start one or more experiments, the system
captures images on schedule with full metadata and logs, and Phase 3's
dashboard only has to provide a UI on top.

## Deliverables

1. **`labcam/engine/experiment.py`** — the `Experiment` model. Carries
   config (name, camera label, interval, duration, operator, notes),
   computed `started_at` and `planned_stop_at`, and runtime state
   (sequence counter, `next_capture_at`, status:
   `idle`/`capturing`/`finished`/`stopped`/`failed`). Owns its lifecycle:
   `start()`, `tick()`, `finalize(reason)`.

2. **`labcam/engine/storage.py`** — all filesystem writes for an
   experiment:
   - Sanitize experiment name (alphanumeric + hyphens; reject empty).
   - Create folder `experiments/<YYYY-MM-DD>_<name>_<camera-label>/`.
     On collision, append `_2`, `_3`, …
   - Generate image filenames `<NNNN>_<YYYY-MM-DDTHH-MM-SS>.jpg`. Local
     lab time, no offset in filename (colons banned on Windows).
   - Write `metadata.json` at start with known fields; update on
     finalize. **Atomic writes** (tmp + fsync + rename) for
     `metadata.json` and `running_state.json`.
   - Append to `capture_log.txt` — append-only, human-readable, lines
     formatted exactly as in `04_DATA_FORMATS.md`. No atomic rewrites.
   - Save captured frames as JPEG at quality from `settings.json`
     (default 90).

3. **`labcam/engine/scheduler.py`** — the heart of the engine:
   - One process-wide loop (background thread is fine — does not have to
     be `asyncio`). Wakes on the soonest `next_capture_at` across all
     running experiments, with a short floor (e.g. 1 s) to avoid spin.
   - For each due experiment: acquire the **single process-wide capture
     lock** (defined in `labcam/cameras/`), perform open-grab-close via
     `cameras.capture_frame(...)`, save the JPEG, append the log line,
     increment the sequence counter, recompute `next_capture_at`,
     release the lock.
   - **Staggering is implicit** in serialising every capture through one
     lock — two cameras can never be open at the same time, even if the
     scheduler runs multiple worker threads.
   - **Retries on capture failure:** retry up to `capture_retries` times
     (from `settings.json`, default 2). Each retry logs an `ERROR` line.
     On total failure, log `failed after retries; sequence gap recorded`
     and continue — **the running experiment is never killed by a
     scheduled-capture failure.** The next scheduled capture uses the
     next monotonic sequence number, leaving a gap.
   - **Finalize** when `now >= planned_stop_at`: write `STOP` log line
     with `reason=completed`, update `metadata.json` (`ended_at`,
     `end_reason`, `images_captured`), remove from
     `running_state.json`.
   - **Stop early** API: caller sets a flag; on next loop iteration the
     experiment is finalized with `end_reason="stopped_early"`.

4. **`labcam/engine/state.py`** — the `config/running_state.json`
   manager:
   - Read on startup (used by `main.py` later in Phase 3, but the API
     lives here in Phase 2).
   - **Startup recovery (Option A):** for every entry found in
     `running_state.json` at process start, update the corresponding
     `metadata.json` with `ended_at=<startup time>` and
     `end_reason="unknown"`, append a `STOP reason=unknown` log line,
     then clear `running_state.json`. **Do not auto-resume.**
   - Atomic writes (tmp + fsync + rename) on every change.
   - Schema exactly per `04_DATA_FORMATS.md`.

5. **Engine API for callers** (used by Phase 3's web server):
   - `start_experiment(config) -> experiment_id` — see start rules below.
   - `stop_experiment(experiment_id)` — early stop.
   - `list_experiments() -> [...]` — running + recently finished status.
   - `latest_frame_path(experiment_id) -> Path | None`.

## Start-of-experiment rules (precise)

- **One active experiment per camera/station.** Start fails with a clear
  error if the chosen camera label already has a running experiment.
- **Pre-flight: disk space check.** Estimate worst-case JPEG count
  (`duration_hours * 60 / interval_minutes` + buffer) × a conservative
  per-image size; fail start fast if free space on `experiments_dir` is
  clearly insufficient. Conservative-per-image-size constant lives in
  one place in the module so it can be tuned.
- **Pre-flight: write `metadata.json`** for the new folder with known
  fields and `ended_at: null`.
- **t=0 baseline capture** happens immediately on start, *inside* the
  start call, holding the capture lock. If the baseline fails after
  `capture_retries`:
  - Append `ERROR` and `STOP reason=baseline_failed` log lines.
  - Delete (or leave but mark) the folder — **leave it** for forensic
    value, with `metadata.json` set to `ended_at=<now>`,
    `end_reason="baseline_failed"`, `images_captured=0`.
  - Return failure to the caller. **No entry is added to
    `running_state.json`.**
- On successful baseline: register in `running_state.json` and set
  `next_capture_at = started_at + interval`.

## Constraints (Phase 2)

- **Nothing in `labcam/engine/` imports `cv2`.** All camera I/O goes
  through `labcam/cameras/` — Phase 1's interface.
- **All capture paths** (baseline, scheduled, future preview) **route
  through the same process-wide capture lock**, defined inside
  `labcam/cameras/`. Phase 2 must use it, not invent its own.
- **One failed scheduled capture never kills the run.** Baseline
  capture is the only capture whose failure stops the experiment.
- **Atomic writes** for `metadata.json` and `running_state.json`.
  `capture_log.txt` is append-only and does not need atomic rewrites.
- **Local lab time** in ISO-8601 with offset for JSON and logs;
  filenames omit the offset and use `HH-MM-SS` (Windows-compatible).
- **No database, no ORM, no SQLite.** Files only.

## Testing (Phase 2)

Run from a small driver script — no UI yet.

1. **Single experiment, short duration:** 2-minute duration, 20-second
   interval. Expect: folder with ~7 images named correctly (0000…0006),
   `metadata.json` with all fields populated and `end_reason=completed`,
   `capture_log.txt` with matching `START` / `CAPTURE` / `STOP` lines,
   no stragglers.
2. **Two concurrent experiments on two cameras** with the same short
   profile. Confirm: every `CAPTURE` line in each log is timestamped
   such that no two captures overlap (i.e., the lock is doing its job).
3. **Induced capture failure:** mock or unplug a camera mid-run. Expect:
   `ERROR` lines, then a sequence gap in the next successful capture,
   and the experiment continues to `completed`.
4. **Baseline failure:** point at a non-existent camera id. Expect:
   `start_experiment` returns failure; no entry in
   `running_state.json`; folder either absent or finalized with
   `end_reason="baseline_failed"` and `images_captured=0`.
5. **Crash recovery (Option A):** start an experiment, kill the
   process. Restart and call the startup-recovery routine. Expect:
   `metadata.json` marked `end_reason="unknown"`,
   `running_state.json` empty.
6. **Disk-space pre-flight:** run with `experiments_dir` pointed at a
   nearly-full volume (or stub the free-space check). Expect: start
   fails fast with a clear error.

## Out of scope for Phase 2

- The web dashboard and `main.py` — Phase 3.
- Live preview path through the engine — Phase 3 (the dashboard's
  preview route calls `labcam.cameras.preview_frame` directly through
  the lock; the engine doesn't need a preview API).
- Auto-resume of crashed experiments — Option B, future extension.
- Camera-disconnect graceful handling beyond "log and continue" —
  Phase 5 hardening adds richer surfacing.

## Definition of done

- A driver script can start, run, and finalize one or more concurrent
  short experiments end-to-end on the Mac dev machine, producing
  folders that match `04_DATA_FORMATS.md` exactly.
- All six test scenarios above pass.
- No `cv2` imports outside `labcam/cameras/`. No OS branching outside
  `labcam/cameras/`.
- `HANDOFF.md` updated with the next phase (3) and any open issues.
