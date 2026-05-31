# Phase 6 Task 5 — Cloud-Synced Storage Guidance

This is a documentation and UI-guidance task, not direct cloud
integration.

## Goal

Help labs back up experiment data using local sync folders while making
it clear that Lab Imaging captures to local files and does not require
internet access.

## In Scope

- Add lab-facing guidance to README and Settings/Storage UI.
- Explain supported pattern:
  save to a local folder managed by OneDrive, Google Drive Desktop,
  Dropbox, Synology Drive, or a network sync tool.
- Explain that syncing should happen after files are written locally.
- Warn against relying on browser uploads or internet availability
  during active capture.
- Link this guidance from save-location settings.

## Out of Scope

- No direct OneDrive, Google Drive, Dropbox, Synology, S3, or FTP APIs.
- No authentication or cloud token handling.
- No background upload worker.
- No sync status tracking.
- No dependency on internet availability.

## Implementation Notes

- This task may be implemented together with Task 4 if useful, but it
  must remain guidance-only.
- Recommended wording should tell operators to choose a normal local
  folder first, then let their existing sync software copy it.
- The app should not inspect or control the sync client.

## Invariants

- Capture writes local files first.
- The experiment folder remains portable without special tools.
- No network dependency is added to capture.

## Test Scenarios

1. **README guidance:** lab staff can identify the supported backup
   pattern.
2. **Settings guidance:** storage settings explain local sync folders
   without promising cloud upload.
3. **Offline clarity:** docs state experiments continue without internet.

## Acceptance Criteria

- Cloud backup expectations are clear and conservative.
- No cloud dependency or credential handling is added.
