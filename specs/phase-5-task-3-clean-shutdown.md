# Phase 5 Task 3 — Clean Shutdown Semantics

This is the implementation spec for graceful app shutdown. It defines
what happens when the lab operator stops the app intentionally.

## Goal

When the app is stopped cleanly, every active experiment should be
finalized as `stopped_early`, `running_state.json` should be cleared,
and the next startup should not mistake the shutdown for a crash.

## In Scope

- Handle process shutdown from:
  - `Ctrl-C` / SIGINT;
  - SIGTERM;
  - Flask server stop path when `labcam.main` exits normally.
- Finish any in-progress capture safely before finalizing active
  experiments.
- Finalize each active experiment with:
  - `ended_at=<shutdown time>`;
  - `end_reason="stopped_early"`;
  - current `images_captured`.
- Append a clear `STOP reason=stopped_early` line to each active
  experiment log.
- Remove active experiments from `running_state.json`.
- Preserve existing crash recovery behavior for unclean exits:
  stale `running_state.json` entries discovered on startup still become
  `end_reason="unknown"`.

## Out of Scope

- No auto-resume after clean shutdown.
- No auto-resume after crash.
- No UI confirmation dialog for shutdown.
- No Windows service installer or app packaging changes.
- No change to the dashboard Stop button semantics; stopping one
  experiment remains separate from stopping the app.

## Implementation Notes

- Add an engine method for clean shutdown finalization, separate from
  the current thread-stop-only `shutdown()` behavior.
- The method should:
  - prevent new captures from being scheduled;
  - wait for the current capture lock/capture attempt to finish when
    practical;
  - finalize all still-active experiments;
  - clear running-state entries.
- `labcam.main` should call the clean shutdown path in its `finally`
  block.
- Signal handling should be small and explicit. If a signal arrives,
  request clean shutdown and let the main process exit normally.
- If clean finalization itself fails because storage is unavailable,
  write as much evidence as possible and allow startup recovery to mark
  any remaining stale entries as `unknown`. Do not hide such failure.
- Use local lab time with timezone offset for shutdown timestamps.

## Invariants

- Stills only; no video or streaming.
- The capture lock remains authoritative; do not interrupt a camera
  while it is open.
- `metadata.json` and `running_state.json` writes remain atomic.
- `capture_log.txt` remains append-only.
- Clean shutdown never writes `end_reason="unknown"`.
- Crash recovery remains Option A and does not resume experiments.
- No `cv2` import outside `labcam/cameras/base_capture.py`.

## Test Scenarios

1. **No active experiments:** start and stop the app. Expect no errors
   and an empty/absent running state.
2. **One active experiment:** start a short run, trigger clean shutdown,
   then inspect metadata/log/state. Expect `stopped_early`, a STOP log
   line, and no running-state entry.
3. **Two active experiments:** both active runs are finalized
   independently with `stopped_early`.
4. **Shutdown during capture:** simulate a slow capture and request
   shutdown while it is in progress. Expect the capture path to finish
   or fail normally before finalization; no camera is left open.
5. **Crash behavior unchanged:** simulate an unclean process exit with
   stale `running_state.json`. On next startup, expect
   `end_reason="unknown"` as before.

## Acceptance Criteria

- Clean shutdown produces a clear stopped state, not crash recovery.
- No active experiment remains in `running_state.json` after clean
  shutdown.
- Startup recovery still marks true stale state as `unknown`.
- Existing dashboard Stop behavior still works.
- Existing compile and invariant checks pass:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools`
  - `rg "cv2\\.imshow" -n labcam tools`
  - `rg "^opencv-python($|[<=>])" -n requirements.txt`
