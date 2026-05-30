# Phase 6 Task 3 — Settings Page

This spec introduces a central dashboard page for safe system settings
and diagnostic information.

## Goal

Give lab staff and future maintainers one obvious dashboard location for
system configuration and diagnostic context, without exposing unsafe
controls.

## In Scope

- Add a Settings page to the dashboard navigation.
- Show current settings from `config/settings.json`.
- Allow editing only safe v1 settings:
  - default interval minutes;
  - default duration hours;
  - JPEG quality;
  - capture retries;
  - warmup frames.
- Show read-only diagnostic/about information:
  - app version or commit if available;
  - Python/OpenCV versions;
  - configured experiments directory;
  - camera config path.
- Write settings atomically.

## Out of Scope

- No LAN/auth/security controls.
- No direct camera mapping edits. Use Task 2.
- No save-location picker in this task. Use Task 4.
- No package/installer work.
- No cloud integration.

## Implementation Notes

- Keep `allow_lan_access` visible but read-only unless a later security
  spec changes it.
- Validate numeric fields before saving:
  - interval and duration must be positive;
  - JPEG quality must be between 1 and 100;
  - retries and warmup frames must be non-negative integers.
- Existing defaults in `config/settings.json.example` remain the
  fallback source for missing keys.
- Changes should affect future runs, not mutate already-running
  experiments.

## Invariants

- Settings remain local JSON files.
- No database is introduced.
- No internet dependency is introduced.
- Unsafe LAN access is not enabled through this task.

## Test Scenarios

1. **View settings:** dashboard displays current values.
2. **Save valid changes:** valid values persist to `settings.json`.
3. **Reject invalid values:** invalid numbers show lab-facing errors and
   do not modify settings.
4. **Running experiment:** changing defaults does not alter active runs.
5. **Missing settings file:** app creates defaults and Settings displays
   them.

## Acceptance Criteria

- Lab staff can safely adjust future-run defaults from the dashboard.
- Developer diagnostics are visible without Terminal.
- Settings writes are atomic and validated.
