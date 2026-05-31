# Phase 6 Task 2 — Dashboard Camera Configuration

This spec moves camera setup workflows into the dashboard while keeping
the existing command-line setup tool as a developer fallback.

## Goal

Lab staff should be able to detect cameras, assign station labels, save
the mapping, and run a basic camera stress test without opening
Terminal or PowerShell.

## In Scope

- Add a dashboard Cameras page.
- Detect available cameras through `labcam/cameras/`.
- Show a fresh still preview for each detected camera.
- Let the operator assign detected cameras to station labels.
- Save `config/cameras.json` using the existing schema.
- Run a dashboard-triggered stress test and display pass/fail counts.
- Preserve `tools/camera_setup.py` unchanged as a fallback.

## Out of Scope

- No continuous live previews.
- No automatic assignment of ambiguous cameras.
- No settings page beyond camera configuration.
- No experiment save-location controls.
- No remote/cloud setup.

## Implementation Notes

- Reuse setup-tool behavior where practical rather than duplicating
  camera identity rules in web code.
- All detection, preview, and stress-test calls must go through
  `labcam/cameras/` APIs.
- Stress-test output should be a simple report:
  `Station 1: 100/100 passed`, plus any failed attempt messages.
- Saving mappings should write `config/cameras.json` atomically.
- The UI should warn clearly when a mapping uses `index_fallback`.

## Invariants

- No OpenCV imports outside `labcam/cameras/`.
- No two cameras open simultaneously.
- Dashboard setup must not require internet access.
- Existing command-line setup remains available.

## Test Scenarios

1. **Detect cameras:** available cameras appear in the Cameras page.
2. **Assign station:** a detected camera can be assigned to a station
   and saved to `config/cameras.json`.
3. **Fallback warning:** `index_fallback` mappings show clear warnings.
4. **Stress test success:** dashboard reports all passes for mock camera
   captures.
5. **Stress test failure:** dashboard reports failed attempts without
   crashing.

## Acceptance Criteria

- A non-technical operator can configure cameras from the dashboard.
- The saved config is compatible with existing engine code.
- Camera access and OpenCV isolation invariants still pass.
