# Phase 5 Task 1 — Station Health & Error Surfacing

This is the implementation spec for the first Phase 5 hardening unit.
It defines how capture health is tracked and surfaced without changing
capture semantics.

## Goal

Make the dashboard clearly show when a running station needs attention:
transient capture failures, repeated capture failures, unavailable
cameras, and existing identity-strategy warnings. Lab staff should see a
plain-language station state instead of needing to inspect terminal
output or `capture_log.txt`.

## In Scope

- Track consecutive scheduled-capture failures per running experiment.
- Clear the failure counter after the next successful scheduled capture.
- Add status payload fields that let `/` render:
  - normal running/idle/finished states;
  - `capture_failing` when a running experiment has repeated capture
    failures;
  - `camera_unavailable` when a configured camera cannot be used;
  - user-facing `health_message` text.
- Keep existing append-only per-experiment logging. The existing retry
  and sequence-gap log lines remain the durable record.
- Use the existing redesigned dashboard states where possible:
  `error` for capture failure and `offline` for camera unavailable.
- Show identity fallback warnings as attention items, but do not mark a
  station broken only because it uses `index_fallback`.

## Out of Scope

- No startup camera verification workflow. That belongs to Phase 6.
- No dashboard camera setup/remapping.
- No live preview or streaming.
- No changes to capture cadence, retry count semantics, or experiment
  folder layout.
- No new database or persistent health store. Runtime health can reset
  when the app process restarts; `capture_log.txt` remains the durable
  evidence.

## Implementation Notes

- Add runtime health fields to `Experiment`, such as
  `consecutive_failures`, `last_error_message`, and `last_error_at`.
- In scheduled capture handling:
  - on success, reset failure fields;
  - after a failed scheduled capture attempt sequence, increment
    `consecutive_failures` and store a sanitized user-facing message;
  - keep the existing sequence-gap behavior so one failed scheduled
    capture never kills the experiment.
- The threshold for `capture_failing` is 3 consecutive failed scheduled
  captures. One or two failures remain visible as warning detail if
  useful, but the station should not move to the red/error state until
  the threshold is reached.
- Do not expose raw exception text if it contains developer-specific
  OpenCV details. Convert expected camera/capture failures to messages
  such as `Camera is not responding. Check the USB connection.`
- Extend `/api/status` station objects with additive fields only:
  `health_state`, `health_message`, `consecutive_failures`,
  `last_error_at`, and `warnings`.
- `health_state` values:
  - `ok`
  - `identity_warning`
  - `capture_warning`
  - `capture_failing`
  - `camera_unavailable`
- Dashboard rendering should use existing card styles before adding new
  styling. Avoid redesigning the dashboard in this task.

## Invariants

- Stills only; no video or streaming.
- Every preview/baseline/scheduled capture remains open-grab-close.
- The single process-wide capture lock remains the only path to camera
  access.
- No `cv2` import outside `labcam/cameras/base_capture.py`.
- No OS-specific camera behavior outside `labcam/cameras/`.
- Files remain the dataset; no database.

## Test Scenarios

1. **No failures:** a running experiment reports `health_state="ok"` and
   the dashboard remains in the normal running state.
2. **Single scheduled failure:** inject one scheduled capture failure.
   Expect an `ERROR` log line and sequence gap behavior unchanged; the
   experiment continues.
3. **Three consecutive scheduled failures:** inject three failures.
   Expect `consecutive_failures=3`, `health_state="capture_failing"`,
   a user-facing dashboard message, and the experiment still running.
4. **Recovery after failure:** after the failing state, inject a
   successful capture. Expect `consecutive_failures=0`,
   `health_state="ok"`, and the dashboard warning cleared.
5. **Configured camera unavailable:** simulate a configured camera that
   cannot be opened. Expect `health_state="camera_unavailable"` and a
   clear dashboard message.

## Acceptance Criteria

- `/api/status` exposes additive health fields without breaking existing
  dashboard clients.
- The dashboard clearly distinguishes normal, warning, error, and
  unavailable station states.
- Capture failures remain non-fatal until another Phase 5 task
  explicitly defines a terminal condition such as disk full.
- Existing compile and invariant checks pass:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools`
  - `rg "cv2\\.imshow" -n labcam tools`
  - `rg "^opencv-python($|[<=>])" -n requirements.txt`
