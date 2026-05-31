# Phase 6 Task 4 — Configurable Experiment Save Location

This spec lets lab staff choose where future experiment folders are
stored while preserving local-first capture behavior.

## Goal

Allow the experiment output directory to be changed from the dashboard,
with clear validation before future runs use the new location.

## In Scope

- Add save-location controls to the Settings page.
- Show the current `experiments_dir`.
- Let the operator enter or choose a local filesystem path.
- Validate that the path exists or can be created.
- Validate write access with a temporary file.
- Apply the new location only to future experiments.

## Out of Scope

- No moving existing experiments.
- No cloud API integration.
- No native OS folder picker unless it is already available without a
  new framework.
- No network-drive guarantee beyond normal filesystem write validation.

## Implementation Notes

- Store the selected location in `config/settings.json` as
  `experiments_dir`.
- Relative paths remain relative to the project root; absolute paths are
  allowed.
- Validation should fail with clear messages for missing, read-only, or
  non-directory paths.
- Running experiments continue writing to the paths they started with.
- The README should mention that users may choose a local folder managed
  by a sync tool, but capture itself stays local.

## Invariants

- The experiment folder remains the dataset.
- No database is introduced.
- The app must not depend on internet access during capture.
- Active experiment folders are never moved automatically.

## Test Scenarios

1. **Valid local path:** settings save and a new experiment writes there.
2. **Relative path:** relative locations resolve consistently.
3. **Read-only path:** validation blocks the change.
4. **Active run:** changing settings does not move or interrupt active
   output.
5. **Restart:** saved location persists after app restart.

## Acceptance Criteria

- Future experiment location can be changed without editing JSON by
  hand.
- The app verifies write access before saving the setting.
- Existing data remains untouched.
