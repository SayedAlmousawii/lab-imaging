# Phase 6 Task 7 — Experiment Browser

This spec adds a dashboard view for reviewing previous experiment
folders.

## Goal

Lab staff should be able to find and inspect previous experiment output
from the dashboard without browsing the filesystem manually.

## In Scope

- Add an Experiments page.
- Scan the configured `experiments_dir` for experiment folders.
- Show a list with date, experiment name, station, status/end reason,
  image count, and folder path.
- Add filters for date and station.
- Add a detail view with metadata, capture log summary, post-run notes
  if present, and image thumbnails.
- Open latest or selected images as still thumbnails only.

## Out of Scope

- No timelapse export.
- No image annotation tools.
- No computer vision analysis.
- No database indexing.
- No moving, deleting, or renaming experiment folders.

## Implementation Notes

- Treat `metadata.json` as the source of truth when present.
- Folders with missing or malformed metadata should appear as
  incomplete with a lab-facing warning, not crash the page.
- Thumbnail rendering should read existing JPEG files and avoid
  modifying experiment folders.
- Keep scan behavior simple enough for the expected folder count; add
  pagination only if needed during implementation.

## Invariants

- Experiment folders remain the dataset.
- Browser views are read-only in this task except for post-notes links
  if Task 6 has landed.
- No database is introduced.

## Test Scenarios

1. **List experiments:** completed folders appear in the browser.
2. **Filter by station/date:** filters narrow the list correctly.
3. **Detail view:** metadata, folder path, log summary, and thumbnails
   render.
4. **Malformed folder:** bad or missing metadata shows a warning.
5. **Large image count:** page remains usable with many images.

## Acceptance Criteria

- Users can find prior runs and inspect their basic outputs from the
  dashboard.
- The feature does not mutate experiment data.
- Missing or malformed folders are handled gracefully.
