# Phase 5 Task 2 — Mid-Run Disk-Full Handling

This is the implementation spec for Phase 5 storage-failure hardening.
It builds on Task 1 station health fields and defines when a storage
failure becomes terminal for one experiment.

## Goal

If an experiment cannot save images mid-run because storage is full or
not writable, the app should stop attempting future captures for that
experiment, record a clear reason, and keep the rest of the system
running.

## In Scope

- Detect save/write failures during scheduled capture.
- Classify likely storage failures separately from camera capture
  failures.
- Mark the affected experiment as failed with
  `end_reason="disk_full"` or `end_reason="storage_failed"`; use
  `disk_full` when the failure is specifically insufficient free space.
- Append clear `ERROR` and `STOP` log lines to `capture_log.txt`.
- Update `metadata.json` atomically with `ended_at`, `end_reason`, and
  the number of successfully saved images.
- Remove the experiment from `running_state.json` so it is no longer
  attempted.
- Surface the terminal condition through `/api/status` and the
  dashboard with a lab-facing message such as
  `Storage is full or not writable. Free space and start a new run.`

## Out of Scope

- No automatic retry loop after a terminal storage failure.
- No auto-resume when space becomes available.
- No moving existing experiments to another folder.
- No settings UI or save-location picker. Configurable save location is
  Phase 6.
- No direct cloud integration.

## Implementation Notes

- Keep the existing start-time disk preflight unchanged.
- During scheduled capture, treat failures from `save_frame_as_jpeg`,
  `save_jpeg_func`, metadata finalization, or append-log writes as
  storage-related only when they are clearly file-system errors
  (`OSError`, `StorageError`, or an explicit disk-usage check showing
  low free space).
- Do not classify camera-open/read failures as disk failures.
- Add a terminal experiment reason for disk/storage failure. The exact
  public values are:
  - `disk_full`
  - `storage_failed`
- If the image write succeeds but final metadata/log write fails, prefer
  the safest recoverable behavior: stop the affected experiment, attempt
  best-effort final metadata/log updates, and surface the storage error.
- Other active experiments continue unless they share the same failing
  storage path and encounter their own write failures.
- This task may add a helper for user-facing storage-error messages, but
  it must not introduce a new persistence layer.

## Invariants

- Stills only; no video or streaming.
- Every capture remains open-grab-close and routed through the global
  capture lock.
- One failed ordinary camera capture still logs/retries/records a
  sequence gap and continues; only storage failure becomes terminal in
  this task.
- `metadata.json` and `running_state.json` writes remain atomic.
- `capture_log.txt` remains append-only.
- No `cv2` import outside `labcam/cameras/base_capture.py`.
- Files remain the dataset; no database.

## Test Scenarios

1. **Start preflight unchanged:** with insufficient free space at start,
   `start_experiment` still fails before baseline capture as today.
2. **Camera failure is not disk failure:** inject a camera-read failure
   during scheduled capture. Expect existing retry/sequence-gap behavior,
   not `disk_full`.
3. **Image write failure:** inject a save/JPEG write failure. Expect the
   experiment to finalize with `storage_failed`, leave other runs alive,
   remove the running-state entry, and show a dashboard storage message.
4. **Low free space write failure:** simulate low free space at the time
   of a write failure. Expect `end_reason="disk_full"`.
5. **Metadata/log evidence:** after a terminal storage failure, inspect
   `metadata.json`, `capture_log.txt`, and `running_state.json` for a
   consistent stopped/failed state.

## Acceptance Criteria

- A mid-run storage failure does not crash the app process.
- The affected experiment stops attempting captures and is not left in
  `running_state.json`.
- Lab staff can see the storage problem from the dashboard without
  reading terminal output.
- Existing capture retry semantics for non-storage failures remain
  unchanged.
- Existing compile and invariant checks pass:
  - `.venv/bin/python -m compileall labcam tools`
  - `rg "import cv2|from cv2" -n labcam tools`
  - `rg "cv2\\.imshow" -n labcam tools`
  - `rg "^opencv-python($|[<=>])" -n requirements.txt`
