# Phase 4 — Windows Verification

This is the authoritative spec for Phase 4 work. It consolidates the
Phase 4 section of `05_BUILD_PLAN.md` with the cross-platform strategy
from `02_ARCHITECTURE.md`. If anything in the broader specs contradicts
this file for Phase 4 scope, this file wins for Phase 4.

**Phase 4 is mandatory before go-live.** No part of v1 is "done" until
this phase passes on real Windows hardware with the real webcams.

## Goal

Prove that the Mac-developed system runs reliably on the actual target:
a Windows lab machine with multiple USB webcams behind a powered hub.
Fix any quirks encountered, but only inside `labcam/cameras/` —
nothing above that boundary should change.

## Deliverables

1. **`labcam/cameras/identify_windows.py`** — Windows-side counterpart
   to `identify_macos.py` from Phase 1. Uses OpenCV's DirectShow backend
   (`cv2.CAP_DSHOW`). Same interface contract as the macOS module:
   reports `identity_strategy`, `stable_id`, `last_seen_index`, and
   `warnings` per camera. Identity-strategy preference order on
   Windows:
   - `hardware_id` (device instance ID / serial — via WMI or
     `setupapi`, whichever is reachable from Python without heavy
     deps; the helper module is allowed small `pywin32` or `wmi`
     dependencies if needed — add to `requirements.txt`).
   - `usb_port` (USB port path from the same enumeration sources).
   - `index_fallback` — warn loudly.

2. **A documented test pass** — short report in `HANDOFF.md` (or a
   `specs/phase-4-report.md` if it grows long) covering each scenario
   below with pass/fail and any observations. This report is the
   green-light artifact for go-live.

## Required test scenarios

All scenarios run on a real Windows lab machine with the real webcams
and a powered USB hub. **No emulation, no Mac substitution.**

1. **Camera enumeration on Windows.** `tools/camera_setup.py` lists
   every connected camera and assigns labels. Save
   `config/cameras.json`; confirm each camera's
   `identity_strategy` is the best available (preferably
   `hardware_id`).

2. **100-cycle open-grab-close stress test per camera** (mirroring the
   Phase 1 Mac stress test). No failures, no resource leaks.

3. **Four concurrent cameras running short experiments through the
   dashboard.** Confirm staggering — every capture serializes
   through the lock; no two cameras are ever open at the same instant.
   Inspect log timestamps to verify.

4. **Identical-device disambiguation** (deferred from Phase 1). With
   at least two identical Logitech C310 units connected, confirm the
   chosen identity strategy correctly distinguishes them — capturing
   from `station1` produces frames from the physical camera labeled
   `station1`, not its identical twin. This is the test Phase 1 could
   not perform.

5. **Reboot survival.** Power-cycle the Windows machine, restart the
   app, confirm `cameras.json` mappings still resolve to the correct
   physical cameras (when the recorded `identity_strategy` claims
   they should).

6. **Replug survival** for `hardware_id` cameras. Unplug and replug a
   camera (same port). Confirm it re-resolves to the same label.

7. **USB-port-move test** for `usb_port` cameras (if any exist).
   Confirm the warning behaves correctly: moving the camera to a
   different port breaks the mapping in the documented way (and the
   UI surfaces this).

8. **Real multi-hour run.** One experiment, 4+ hours, default
   interval. Expect: clean folder, complete log, no resource leaks,
   no overheating, host CPU/memory steady.

9. **Framing/preview correctness** on a real station rig. Preview
   matches what's actually saved. Lighting/glare as expected. (This
   is a "did we frame the rig well" check, not a software bug
   check — but Phase 4 surfaces it before a long unattended run.)

10. **Dashboard accessible** from the lab machine's own browser on
    `localhost`, and (if `allow_lan_access` is enabled for the test)
    from another machine on the same LAN via the host IP.

## Constraints (Phase 4)

- **All fixes go inside `labcam/cameras/` only.** If a Windows quirk
  requires a change elsewhere, that is a design failure — escalate
  and ask. The whole cross-platform strategy is "isolate OS code in
  one box;" if the box leaks, the design is wrong.
- **The DirectShow backend** (`cv2.CAP_DSHOW`) is the Windows
  default. Do not fall back to MSMF without an explicit reason
  documented in `DECISIONS.md`.
- **Identity-strategy semantics are identical to macOS:** the same
  three terms (`hardware_id`, `usb_port`, `index_fallback`), the
  same warning rules, the same `cameras.json` schema.
- **`opencv-python-headless` only** — never the GUI wheel, even
  temporarily for debugging.
- **No new dependencies above `labcam/cameras/`.** Any Windows-only
  dep (e.g., `pywin32`, `wmi`) lives in `requirements.txt` and is
  only imported inside the `cameras/` package.

## Out of scope for Phase 4

- New features. Phase 4 is verification + bug-fix-in-box only.
- Lab-staff README polish — Phase 5.
- Auto-resume — future extension.
- Auth / HTTPS for LAN dashboards — future extension.

## Definition of done

- Every test scenario above is run on the real Windows lab machine
  with the real webcams and recorded as pass/fail with notes.
- All scenarios pass, or any failure is documented with a fix that
  lives entirely inside `labcam/cameras/`.
- `requirements.txt` reflects any Windows deps added.
- `HANDOFF.md` (or a phase-4 report file) contains the test record
  and is committed.
- `DECISIONS.md` updated with any quirks-and-fixes worth remembering.
