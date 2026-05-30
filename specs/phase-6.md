# Phase 6 — Dashboard Workflow Features

This is the holding spec for post-v1 usability and workflow features
identified after Phase 4 Windows validation. Phase 6 starts only after
Phase 5 hardening is complete or explicitly paused.

Phase 6 is intentionally separate from Phase 5: Phase 5 hardens the
current capture system for lab use; Phase 6 adds new dashboard-driven
workflows that reduce dependence on Terminal/PowerShell and improve
post-run review.

## Goal

Make Lab Imaging more self-service for researchers while preserving the
core capture invariants: local-first storage, still-image datasets,
single-machine v1 operation, and explicit camera access control.

## Candidate Feature Specs

Each item below should become its own implementation spec before code
work begins.

1. **Startup camera verification workflow**
   - On app startup, guide the user through confirming detected camera
     previews against station labels.
   - Suggest previous mappings but make preview confirmation the
     user-facing source of truth when identity is weak.
   - Save confirmed mappings for future sessions.
   - This is the highest-priority Phase 6 candidate because Windows
     validation showed `index_fallback` may be the honest mapping on
     some hardware.

2. **Dashboard-based camera configuration**
   - Move list/setup/stress-test workflows into the dashboard while
     keeping `tools/camera_setup.py` available for developers.
   - Include camera detection, station assignment, preview confirmation,
     and a dashboard-triggered stress-test report.

3. **Settings page**
   - Centralize system settings such as experiment storage location,
     camera mapping access, diagnostic/about information, and future
     safe configuration switches.

4. **Configurable experiment save location**
   - Allow users to choose where future experiments are stored.
   - Validate write access before saving.
   - Existing experiments remain where they are.

5. **Cloud-synced storage guidance**
   - Support cloud backup by saving locally into a folder managed by
     OneDrive, Google Drive Desktop, Dropbox, Synology Drive, or a
     network sync tool.
   - The app must never depend on internet availability for capture.
   - Direct cloud APIs are out of scope unless a later spec explicitly
     changes this.

6. **Post-experiment notes**
   - Let researchers add notes after a run completes.
   - The storage shape must be specified before implementation
     (`metadata.json`, `notes.txt`, or append-only note log).

7. **Experiment browser**
   - Let users review previous experiments from the dashboard.
   - Initial scope may include experiment list, date/station filters,
     metadata view, folder path, and image thumbnails.
   - Timelapse generation/export tools are future extensions unless a
     dedicated spec brings them in.

8. **Maintenance mode during experiments**
   - Allow a running experiment to enter a documented adjustment window.
   - Captures pause, the gap is logged, and the user resumes the run
     explicitly.
   - Requires careful scheduler and metadata semantics before coding.

9. **Live preview / repeated preview investigation**
   - Continuous live preview is not a Phase 5 feature.
   - A future spec must decide whether to keep repeated fresh stills or
     intentionally revise the preview invariant with a camera manager
     that preserves safe locking and never conflicts with scheduled
     capture.

## Constraints

- Do not weaken the core rule that scheduled capture produces still
  images, not video.
- Do not let any dashboard workflow open two cameras at the same time.
- Keep OpenCV and OS-specific camera behavior inside `labcam/cameras/`.
- Keep Terminal tools available as developer/debug fallbacks even after
  dashboard workflows exist.
- Preserve local-first operation. Cloud sync, if used, sits outside the
  capture path.

## Suggested Ordering

1. Startup camera verification workflow.
2. Dashboard camera configuration and stress test.
3. Settings page plus configurable save location.
4. Experiment browser.
5. Post-experiment notes.
6. Maintenance mode and any live-preview investigation.
