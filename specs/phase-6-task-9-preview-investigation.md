# Phase 6 Task 9 - Preview Recommendation

This task closes the live preview / repeated preview investigation as a
design recommendation. It does not add production preview code.

## Recommendation

Keep production preview as repeated fresh still captures for the current
Phase 6 completion path. Do not add continuous live preview, a streaming
endpoint, or a long-lived camera manager unless a later implementation
spec explicitly changes the preview model and is validated on Windows
hardware.

The current preview model best preserves the core invariants:

- preview uses open-grab-close capture;
- every preview path routes through the same capture safety checks as
  scheduled capture;
- no production path intentionally holds a camera open between captures;
- scheduled experiment capture remains still-image based;
- OS and OpenCV behavior stays isolated in `labcam/cameras/`.

## Model Comparison

### Repeated Fresh Stills

Repeated fresh stills keep the existing camera lifetime model. Each
preview request opens the camera, captures a frame, saves or returns one
JPEG, and closes the camera. This makes preview behavior easy to reason
about because it has the same shape as baseline and scheduled captures.

Benefits:

- Preserves the v1 "stills, not video" architecture.
- Avoids long-lived camera ownership and driver state.
- Works with the existing process-wide capture safety model.
- Keeps preview failures isolated to a single preview request.
- Fits maintenance mode because a maintenance preview is just another
  explicit fresh still.

Tradeoffs:

- Framing and focus feedback is slower than a true video feed.
- Users must click preview again, or a future UI must perform bounded
  repeated refresh.
- Frequent preview refresh still competes for camera time and must show
  clear busy feedback during scheduled capture windows.

### Continuous Live Preview

Continuous live preview would intentionally change camera lifetime
semantics. A camera manager would need to decide which camera may stay
open, how preview stops before scheduled captures, how other stations
queue or fail preview requests, and how Windows USB/OpenCV driver
failures are recovered.

Risks:

- A live camera can conflict with scheduled capture unless ownership is
  centrally coordinated and preemptible.
- Holding cameras open increases exposure to USB hub, driver, and
  OpenCV backend quirks, especially on the Windows lab target.
- Multi-station preview can accidentally pressure the "never two
  cameras open simultaneously" invariant.
- Maintenance mode becomes ambiguous unless preview is explicitly
  defined as a pause-only, preemptible, non-recording operation.
- A streaming endpoint would expand the dashboard surface and must be
  specified, tested, and validated separately.

## Interaction Rules

Any future repeated-still UX improvement must follow these rules:

- `POST /api/preview` remains open-grab-close and returns one fresh JPEG.
- Button-triggered preview remains valid on the New Experiment,
  verification, camera configuration, and maintenance workflows.
- A future auto-refresh UI may request repeated stills only at a bounded
  cadence and only while the relevant control/view is active.
- Auto-refresh must stop or skip when the selected camera is scheduled,
  capturing, being configured, or otherwise reported busy.
- Busy conflicts must show explicit dashboard feedback instead of
  silently queueing behind scheduled capture.
- Preview refresh must not write into an experiment `images/` folder,
  advance sequence numbers, or change `metadata.json` image counts.

## Future Spec Trigger

Write a separate implementation spec before adding any of the following:

- continuous live preview;
- a streaming preview endpoint;
- a camera manager that keeps cameras open;
- background preview polling that runs without explicit active-user
  context;
- preview behavior that can preempt, delay, or reschedule experiment
  captures.

That future spec must include Windows hardware validation with the real
USB hub and lab webcams, conflict simulation against scheduled capture,
and a clear shutdown/preemption model for every open camera.

## Acceptance Criteria

- A written recommendation exists before any production preview rewrite.
- Risks to camera locking and scheduled capture are explicitly resolved.
- Continuous live preview is rejected for the current Phase 6 completion
  path.
- The repeated-still path has a clear UX improvement plan.
