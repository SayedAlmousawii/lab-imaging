# Phase 6 Task 9 — Live Preview / Repeated Preview Investigation

This is an investigation and design-spec task. It must complete before
any continuous preview implementation.

## Goal

Decide whether Lab Imaging should keep preview as repeated fresh stills
or intentionally add a live-preview mode with a camera manager that
preserves capture safety.

## In Scope

- Compare two preview models:
  - repeated fresh still captures;
  - continuous live preview.
- Document impact on camera ownership, global locking, scheduled
  capture, maintenance mode, and USB stability.
- Prototype only if needed, behind a local throwaway script or branch.
- Produce a final recommendation spec before implementation.

## Out of Scope

- No production live preview in this task.
- No streaming endpoint in this task.
- No frontend live-preview UI in this task.
- No weakening of scheduled still-capture behavior.

## Investigation Questions

- Can repeated fresh stills satisfy framing and focus needs well enough?
- If live preview is required, when must it stop for scheduled captures?
- Does the camera manager hold a camera open, or does it still
  open-grab-close at a faster cadence?
- What happens when multiple stations request preview?
- How does preview interact with maintenance mode?
- What are the Windows USB and OpenCV failure modes?

## Invariants

- Scheduled experiment capture remains still-image based.
- No production path may open two cameras simultaneously.
- OS/OpenCV work remains in `labcam/cameras/`.
- Any change to preview semantics must be explicit in specs before code.

## Test / Evidence Plan

1. **Repeated stills:** measure usability and capture timing with
   repeated still previews.
2. **Live prototype if needed:** test one camera on Windows without
   scheduled capture conflicts.
3. **Conflict simulation:** verify what happens when preview and
   scheduled capture compete.
4. **Recommendation:** write the chosen implementation spec and update
   Phase 6 ordering.

## Acceptance Criteria

- A written recommendation exists before any production preview rewrite.
- Risks to camera locking and scheduled capture are explicitly resolved.
- If live preview is rejected, the repeated-still path has a clear UX
  improvement plan.
