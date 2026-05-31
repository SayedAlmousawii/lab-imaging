# Phase 6 Task 1 — Startup Camera Verification

This is the implementation spec for the first Phase 6 workflow unit.
It turns weak camera identity into an explicit operator confirmation
step before normal dashboard use.

## Goal

When the app starts, lab staff should confirm that each station label
matches the actual camera preview before starting experiments. This is
especially important when the current Windows machine uses
`identity_strategy="index_fallback"`.

## In Scope

- Add a dashboard verification view shown before normal station use when
  camera confirmation is needed.
- Show every configured station label with a fresh still preview.
- Let the operator mark each station as confirmed.
- Persist confirmation data in `config/cameras.json` without changing
  the existing required fields.
- Make weak identity mappings obvious with lab-facing language.
- Allow normal dashboard use only after all configured stations are
  confirmed for the current startup session.

## Out of Scope

- No full camera setup wizard. That is Task 2.
- No stress test UI. That is Task 2.
- No settings page or save-location controls.
- No continuous live preview. Preview remains fresh still capture.
- No automatic camera remapping without operator confirmation.

## Implementation Notes

- Add minimal confirmation metadata to each camera record, such as
  `last_confirmed_at` and `last_confirmed_index`, while preserving
  `label`, `identity_strategy`, `stable_id`, `last_seen_index`,
  `warnings`, and `notes`.
- The verification view should use the existing preview path so all
  camera access still routes through the global capture lock.
- Startup should route `/` and `/new` to verification until all cameras
  are confirmed, but API status should remain readable.
- If a camera preview fails, show that station as unavailable and do not
  let it be confirmed.
- If there are no configured cameras, keep the existing missing config
  behavior that points to setup.

## Invariants

- Preview is a fresh still, not video or a stream.
- No two cameras may be open at once.
- No `cv2` or OS-specific camera logic outside `labcam/cameras/`.
- `config/cameras.json` remains the camera mapping file.
- Terminal setup tools remain available.

## Test Scenarios

1. **Strong identity cameras:** startup shows previews and allows
   confirmation.
2. **Index fallback cameras:** startup shows a clear warning and allows
   manual confirmation.
3. **One unavailable camera:** the failed station cannot be confirmed;
   the dashboard shows a clear unavailable message.
4. **Confirmed session:** after all stations are confirmed, `/` and
   `/new` are usable.
5. **Restart:** confirmation metadata persists in `cameras.json`, but a
   new process still requires startup confirmation when identity is weak.

## Acceptance Criteria

- Lab staff can verify station labels from the dashboard without using
  Terminal.
- Experiments cannot start before required startup confirmation.
- Camera access invariants still pass.
- Existing Phase 5 driver scenarios still pass.
