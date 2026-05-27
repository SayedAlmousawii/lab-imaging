# Decisions Log

Append-only log of non-trivial decisions made on this project. Each entry:
**Decided** / **Why** / **Considered and rejected**. Newest entries at the
bottom under their date heading.

---

## 2026-05-27 — Initial planning

### 1. Periodic stills, not continuous video

- **Decided:** Capture one JPEG per camera per fixed interval (5–10 min
  default), not video.
- **Why:** Measurements are sampled by eye every few minutes; video is
  unnecessary. Stills eliminate the storage/overheating/encoding-failure
  problems that made the phone-based workflow unreliable for 7–20 hour
  runs. A 20-hour run becomes ~120–240 images instead of millions of
  frames.
- **Considered and rejected:** Continuous video capture from USB webcams
  (storage + reliability + heat); periodic short video clips (still huge,
  no benefit over a still for manual reading).

### 2. Open-grab-close per capture, with a process-wide capture lock

- **Decided:** For every capture (scheduled or preview), open the camera,
  discard warm-up frames, grab one frame, save, then close. All capture
  paths in the entire program go through a single process-wide capture
  lock so two cameras are **never open simultaneously**.
- **Why:** The camera is active only a few seconds out of every 5–10
  minutes, which eliminates USB-bandwidth contention, heat, and the
  classic "4 USB cameras max" limit (that limit is for continuous
  streaming). Staggering captures behind a single lock makes the system
  scale past 4 cameras and keeps failure modes simple.
- **Considered and rejected:** Holding cameras open for the duration of
  the experiment (bandwidth + heat + reliability); per-camera locks
  (does not prevent two cameras being open at once).

### 3. Files and folders, no database

- **Decided:** The per-experiment folder *is* the dataset:
  `metadata.json`, `capture_log.txt`, `images/`. The only live-state file
  is `config/running_state.json`. Atomic writes (tmp + fsync + rename)
  for `metadata.json` and `running_state.json`.
- **Why:** Inspectable in any file browser, portable, no service to run,
  no schema migrations, lab staff can copy a folder to a USB stick and
  go. The data outlives the software.
- **Considered and rejected:** SQLite (extra dependency, opaque to lab
  staff, no benefit over folders at this scale); a hosted DB (network
  dependency for a local lab tool).

### 4. Option A crash behavior (accept loss in v1)

- **Decided:** If the program crashes or the host reboots mid-run, the
  captured images so far are kept and the experiment is considered over.
  On startup, any experiment still listed in `running_state.json` is
  finalized with `ended_at=<startup time>` and `end_reason="unknown"`,
  then `running_state.json` is cleared. **No auto-resume in v1.**
- **Why:** Simplest correct behavior. The design stays friendly to
  adding auto-resume later (Option B is a documented future extension)
  without paying its complexity cost now.
- **Considered and rejected:** Option B auto-resume (more state, more
  edge cases — defer until the basic system is proven in the lab); doing
  nothing on startup (leaves stale `running_state.json` and confuses the
  dashboard).

### 5. Explicit `identity_strategy` field on every camera record

- **Decided:** `config/cameras.json` records, per camera, an
  `identity_strategy` of exactly one of: `hardware_id`,
  `usb_port`, or `index_fallback`, alongside the matching `stable_id`,
  `last_seen_index`, and a `warnings` array. The same three terms are
  used verbatim in code, comments, log lines, and any user-facing text.
- **Why:** OpenCV's enumeration alone (integer indices) is not durable
  across reboot/replug. For an unattended multi-station system,
  silently mis-matching cameras is a worst-case bug. Making the chosen
  strategy explicit lets downstream code reason about how confident a
  match is, and lets the dashboard warn the operator when only a weak
  strategy is available.
- **Considered and rejected:** Trusting OpenCV indices alone (unsafe);
  burying the strategy choice in code without persisting it (no audit
  trail, no way for the UI to warn).

### 6. Preview is a button-triggered fresh still, not a stream

- **Decided:** Preview uses the same open-grab-close path as a scheduled
  capture. The dashboard and the setup tool both request previews as
  one-off snapshots; there is no continuous video preview in v1.
- **Why:** Reuses the exact code path that production captures will use,
  so what the operator sees in preview matches what will be saved. Also
  preserves the "never two cameras open at once" invariant trivially —
  preview holds the capture lock briefly like everything else.
- **Considered and rejected:** A live MJPEG / WebRTC preview stream
  (adds dependencies, holds the camera open, duplicates code paths, and
  tempts the system into bypassing the capture lock).

### 7. `opencv-python-headless`, not `opencv-python`

- **Decided:** Use the headless OpenCV wheel
  (`opencv-python-headless`). No `cv2.imshow`, no GUI windows. The setup
  tool writes preview JPEGs to the OS temp directory and prints paths.
- **Why:** No GUI dependencies on the Windows lab machine (no Qt /
  GTK), smaller install, no risk of an accidental `cv2.imshow` call
  blocking an unattended run. Aligns with the "lab computer is headless
  in practice" stance.
- **Considered and rejected:** `opencv-python` (drags in GUI libs we
  never use); a Pillow-only approach (loses the camera-capture API we
  rely on).

### 8. Identical-device validation deferred to Phase 4

- **Decided:** Verifying that the identity strategy disambiguates two
  identical Logitech C310s is deferred to the Phase 4 Windows hardware
  pass.
- **Why:** A second identical webcam is not available on the Mac dev
  machine, so this verification cannot be performed in Phase 1 honestly.
  Phase 4 is the mandatory on-real-hardware test pass anyway.
- **Considered and rejected:** Buying a second identical camera just
  for Mac dev (wasteful — Windows verification is already mandatory);
  shipping without ever testing the identical-device case (unacceptable
  — multi-station deployment depends on it).
