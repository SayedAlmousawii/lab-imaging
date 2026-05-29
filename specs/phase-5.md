# Phase 5 — Hardening & Polish

This is the authoritative spec for Phase 5 work. It expands the Phase 5
section of `05_BUILD_PLAN.md`. By the time Phase 5 starts, the system
works end-to-end on the real Windows lab machine — Phase 5 is the
sand-the-rough-edges pass that gets it into lab-staff hands.

## Goal

Take a working system and make it operable by non-technical lab staff
without supervision. Specifically: surface errors clearly, handle
plausible real-world failure modes gracefully, write the lab-staff
README, and finalize sensible defaults.

Phase 5 is intentionally hardening-only. Post-Phase-4 usability and
workflow features from `specs/post-phase4-brainstorm.md` are deferred to
Phase 6 and tracked in `specs/phase-6.md`.

## Deliverables

1. **Graceful handling of real-world failure modes.** For each item
   below: detect it, log it, surface it in the dashboard, and — where
   safe — keep the rest of the system running.
   - **Camera disconnect mid-run.** Already partially handled by the
     "log + retry + sequence gap" rule from Phase 2. Phase 5 adds:
     dashboard shows the station as "capture failing" (yellow/red
     badge) after N consecutive failures (e.g., 3); when the camera
     comes back, the badge clears on the next successful capture.
     The experiment continues until its planned stop or until the
     human stops it — disconnect alone never kills it.
   - **Disk full.** Phase 2's pre-flight check catches obvious cases
     at start. Phase 5 adds: mid-run write failure raises an `ERROR`
     log line, the dashboard shows the station as "disk full", and
     subsequent captures stop being attempted for that experiment
     (rather than spinning on hopeless writes). Other experiments on
     other paths are unaffected if the volume is local to that
     experiment's path.
   - **App shutdown.** Catch SIGINT / SIGTERM (and the Windows
     console-close equivalent if straightforward). On shutdown:
     finalize the current capture cleanly if mid-lock, then mark
     every running experiment with `end_reason="stopped_early"` and
     `ended_at=<now>` in `metadata.json`, clear `running_state.json`.
     **Do not** mark them `unknown` — clean shutdown is not a crash.
     The `unknown` reason remains reserved for actual crashes
     discovered on next startup.
   - **Camera enumeration failure on startup** (e.g.,
     `cameras.json` references a camera that's no longer connected).
     Surface as a clear startup warning; the dashboard marks that
     station "unavailable" until the camera is reconnected. App does
     not crash.

2. **Clear error surfacing in the dashboard.**
   - A persistent banner area at the top of `/` for system-level
     issues (disk-full warnings, missing camera, identity-strategy
     downgrades).
   - Per-station badges for transient issues (capture failing, no
     longer reachable).
   - All error messages are written for a lab tech, not a developer.
     "Capture failed: camera not responding" — not
     `cv2.error: (-215:Assertion failed)`.

3. **Lab-staff `README.md`** (separate from the developer README from
   Phase 0 — or this becomes the primary one and the dev notes move
   to a `CONTRIBUTING.md`. Phase 5 picks one; recommendation: rename
   the dev one to `CONTRIBUTING.md` and make `README.md` the
   lab-staff doc.) Contents:
   - What the system does, in plain language.
   - Daily-use workflow: start the app, open the dashboard,
     preview a camera, start an experiment, find the results folder
     afterwards.
   - What to do when something goes wrong (camera offline, disk
     full, app won't start).
   - Where the data lives and how to copy it off.
   - When to call the developer.
   - Screenshots if practical.

4. **Sensible defaults in `config/settings.json.example`** finalized
   based on Phase 4 observations. Phase 5 is the moment to revisit
   each default (`warmup_frames`, `capture_retries`,
   `default_interval_minutes`, `default_duration_hours`,
   `jpeg_quality`) and adjust based on what the real hardware
   actually wanted. Document any change in `DECISIONS.md`.

5. **Final pass on `AGENTS.md` and `HANDOFF.md`.** Phase 5 also marks
   v1 complete. `HANDOFF.md` should clearly say so, and list the
   documented future extensions (auto-resume, CV-based detection,
   multi-PC scaling, event-based triggers, LAN auth) so a future
   session doesn't think they're TODOs.

## Constraints (Phase 5)

- **No new features beyond hardening and docs.** Phase 5 is not the
  place to add CV detection or auto-resume. Those are explicitly
  v2 territory.
- **No Phase 6 workflow features.** Startup camera verification,
  dashboard camera configuration, settings pages, configurable save
  location, post-experiment notes, experiment browser, maintenance mode,
  and live-preview changes are not part of Phase 5 unless the human
  explicitly reopens the phase boundary.
- **All fixes that touch OS / camera behavior stay inside
  `labcam/cameras/`.** Same boundary as always.
- **Error messages are user-facing.** Audit every string a lab tech
  could see and rewrite for clarity.
- **Defaults must be safe-by-default.** `allow_lan_access` stays
  `false`. `jpeg_quality` stays high (90+). `capture_retries`
  positive.

## Testing (Phase 5)

- **Camera disconnect on a running experiment.** Pull the USB cable,
  wait long enough for the failure badge to appear, plug it back in,
  confirm the badge clears and captures resume.
- **Simulated disk-full** mid-run (point `experiments_dir` at a
  small volume or a `tmpfs` of known size). Confirm the system
  reaches the documented "stopped because disk full" state and
  doesn't crash.
- **Ctrl-C / Stop service.** Confirm `metadata.json` and
  `running_state.json` end up in the documented "clean shutdown"
  state.
- **Bad `cameras.json` reference.** Edit `cameras.json` to point
  one entry at a disconnected camera; start the app; confirm
  graceful "unavailable" handling.
- **Lab-staff README dry-run:** hand the README to a lab staffer (or
  someone playing one) and have them follow it cold. Note every
  place they get confused — fix the README.

## Out of scope for Phase 5 (= out of scope for v1)

Documented so the next session doesn't accidentally start building them:
- **Auto-resume after crash/reboot** (Option B). The design supports
  adding it later; v1 ships without it.
- **Automatic level detection** (computer vision reading the ruler).
  Manual reading is the v1 workflow; the captured image corpus is
  what a future CV pass would train/test on.
- **Multi-PC scaling.** A second Windows machine running the same
  software with a combined status view. v1 is single-machine.
- **Event-based triggers** (motion / color change) instead of fixed
  interval. v1 is interval-only.
- **Hardened LAN / remote access** with auth and HTTPS. v1 is
  trusted-network only.

## Definition of done

- All five test scenarios above pass on the real Windows lab machine.
- A non-technical user can run a real experiment end-to-end using only
  the lab-staff `README.md` for guidance.
- `README.md` and (if introduced) `CONTRIBUTING.md` are finalized.
- `config/settings.json.example` defaults reflect Phase 4 reality.
- `HANDOFF.md` marks v1 as complete and lists the future extensions.
- `DECISIONS.md` records any default-tuning decisions made.
