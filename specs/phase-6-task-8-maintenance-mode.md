# Phase 6 Task 8 — Maintenance Mode During Experiments

This spec defines a controlled pause window for active experiments.

## Goal

Allow a researcher to pause scheduled captures during a documented
adjustment window, then explicitly resume the experiment.

## In Scope

- Add a maintenance state for an active experiment.
- Let the operator enter maintenance mode from the status page.
- Pause scheduled captures while maintenance is active.
- Log maintenance start/end and record the skipped capture window.
- Let the operator add a short maintenance note.
- Resume explicitly and continue future scheduled captures.

## Out of Scope

- No continuous live preview unless Task 9 later approves a preview
  model.
- No automatic resume timer in the first implementation.
- No changing original planned duration unless a later spec says so.
- No editing historical image sequences.

## Implementation Notes

- Add maintenance events to `capture_log.txt` and a structured field in
  `metadata.json`, such as `maintenance_events`.
- While in maintenance, the scheduler should not attempt captures for
  that experiment.
- Sequence numbers should remain monotonic. The implementation must
  decide whether skipped scheduled times create explicit sequence gaps
  or only maintenance log entries; record that decision before coding.
- Other experiments on other cameras continue normally.
- The dashboard should make maintenance state visually distinct from
  stopped or failed.

## Invariants

- One experiment per camera remains true.
- No two cameras open simultaneously.
- Captures remain still images.
- Maintenance does not imply crash recovery or auto-resume.

## Test Scenarios

1. **Enter maintenance:** running experiment changes state and stops
   scheduled captures.
2. **Resume:** experiment returns to running and future captures occur.
3. **Log evidence:** maintenance start/end and note are visible in the
   log/metadata.
4. **Other station running:** another camera continues capturing.
5. **Stop during maintenance:** early stop finalizes cleanly.

## Acceptance Criteria

- Maintenance windows are explicit, visible, and auditable.
- Capture scheduling behaves predictably through pause and resume.
- Existing failure and clean-shutdown behavior remains intact.
