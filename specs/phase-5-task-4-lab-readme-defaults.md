# Phase 5 Task 4 — Lab-Staff README & Defaults

This is the implementation spec for the final Phase 5 documentation and
configuration polish unit.

## Goal

Make the project understandable to non-technical lab staff and lock the
safe v1 defaults based on Phase 4 observations.

## In Scope

- Convert the root `README.md` into the lab-staff runbook.
- Move current developer setup notes into `CONTRIBUTING.md`.
- Document the daily operator workflow:
  - start the app;
  - open the dashboard;
  - preview a station;
  - start an experiment;
  - monitor status;
  - stop early when needed;
  - find the experiment folder afterward.
- Document common problems in lab-facing language:
  - camera unavailable;
  - identity fallback warning;
  - capture failing;
  - disk/storage full;
  - missing `config/cameras.json`;
  - app will not start.
- Document where data lives and how to copy it off safely.
- Document that cloud sync should be configured outside the app by
  choosing a local folder managed by OneDrive/Google Drive
  Desktop/Dropbox/etc.; capture must not depend on internet access.
- Review `config/settings.json.example` defaults and adjust only if the
  Phase 4 evidence supports it.
- Record any default changes in `DECISIONS.md`.

## Out of Scope

- No settings UI.
- No native folder picker.
- No direct cloud API integration.
- No packaging/installer work.
- No post-experiment notes or experiment browser.
- No live preview, maintenance mode, or startup camera verification
  workflow.

## Implementation Notes

- The root `README.md` should be written for lab staff first. Keep
  commands minimal and copy-pasteable.
- `CONTRIBUTING.md` should contain developer environment setup,
  architecture pointers, test/check commands, and notes that are not
  useful to lab operators.
- The runbook should be honest about `index_fallback`: if cameras are
  replugged, rebooted, or identical, operators should verify previews
  before long runs.
- Include Windows commands because the lab target is Windows; include
  Mac commands only in `CONTRIBUTING.md` unless needed for developers.
- If screenshots are added, they should be small, local repo assets and
  not required for the README to be useful. Screenshots are optional.
- Defaults review starts from current values:
  - `allow_lan_access=false`;
  - `jpeg_quality=90`;
  - `capture_retries=2`;
  - `default_interval_minutes=5`;
  - `default_duration_hours=12`;
  - `warmup_frames=5`.
- Do not loosen `allow_lan_access`; it remains `false` unless a later
  security/auth spec changes the LAN story.

## Invariants

- Lab-staff docs must preserve still-capture language; do not describe
  video or live streaming.
- Data remains local files; no database.
- Cloud sync, if mentioned, is outside the capture path.
- The README must not promise auto-resume after crash.
- The README must not instruct users to install plain `opencv-python`.

## Test Scenarios

1. **Cold operator read-through:** a non-developer can identify how to
   start the app, start a run, stop a run, and find output data.
2. **Missing camera config:** README tells the operator to run the
   camera setup flow/tool before starting the dashboard.
3. **Identity fallback warning:** README explains the warning and says
   to verify previews after camera changes.
4. **Settings defaults:** every default in `settings.json.example` is
   either retained with rationale or changed with a decision-log entry.
5. **Developer notes preserved:** commands needed by future developers
   still exist in `CONTRIBUTING.md`.

## Acceptance Criteria

- Root README is lab-staff-first and no longer primarily a developer
  setup note.
- Developer setup content is preserved in `CONTRIBUTING.md`.
- `settings.json.example` remains safe-by-default.
- Any default changes are recorded in `DECISIONS.md`.
- Docs clearly distinguish v1 behavior from Phase 6/future features.
