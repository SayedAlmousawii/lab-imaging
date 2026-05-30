# Phase 6 Task 6 — Post-Experiment Notes

This spec adds a way for researchers to record observations after an
experiment has finished.

## Goal

Researchers should be able to add human notes to a completed experiment
from the dashboard without editing files by hand.

## In Scope

- Add a notes editor for completed or stopped experiments.
- Store post-run notes in a plain text file named `post_notes.txt` in
  the experiment folder.
- Preserve original start-time `notes` in `metadata.json`.
- Show note presence in experiment details and browser views.
- Write notes atomically.

## Out of Scope

- No notes on active experiments in this task.
- No rich text editor.
- No multi-user conflict handling.
- No database or search index.
- No automatic analysis of notes.

## Implementation Notes

- `post_notes.txt` is chosen to keep post-run notes readable in a file
  browser and avoid rewriting historical metadata for ordinary edits.
- Notes are editable as one text body.
- If the file does not exist, the UI shows an empty editor.
- Saving an empty note may delete the file or write an empty file; pick
  one behavior in implementation and document it in the spec update if
  needed.

## Invariants

- Experiment folders remain self-contained.
- Notes are local files, not database rows.
- Existing `metadata.json` fields keep their current meaning.

## Test Scenarios

1. **Add note:** completed experiment gets `post_notes.txt`.
2. **Edit note:** existing note text can be changed safely.
3. **No note:** experiments without notes still render normally.
4. **Active run:** active experiments do not show editable post-run
   notes.
5. **Filesystem read:** notes are readable outside the app.

## Acceptance Criteria

- Researchers can add and edit post-run notes from the dashboard.
- The notes file travels with the experiment folder.
- Existing experiment metadata remains compatible.
