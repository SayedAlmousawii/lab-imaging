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

### 9. Process-doc conventions resolved during initialization

These were ambiguous calls made while seeding the scaffolding. Surfacing
them here so a future session can revisit if any feel wrong.

- **Decided:** `AGENTS.md` is *not* dated — it contains invariants only,
  so there is nothing to date. The "dated entries" convention applies
  to `HANDOFF.md`'s session log and to `DECISIONS.md` only. `HANDOFF.md`
  carries an undated "Current state" snapshot at the top plus a dated
  session log below.
  - **Why:** A rulebook of invariants does not benefit from per-rule
    dates; revisions to it should rewrite the rule in place. Dated
    entries make sense where the history matters (decisions log, session
    log) and add noise where it does not (invariants).
  - **Considered and rejected:** Dating every section of `AGENTS.md`
    (would imply rules expire or accrete chronologically, which is
    wrong); keeping `HANDOFF.md` entirely as a dated log with no
    snapshot (forces a new session to read the whole history just to
    learn the current branch and phase).
- **Decided:** "Dated entries" use the human's local lab date, not UTC.
  - **Why:** The whole project uses local lab time for timestamps in
    metadata, logs, and filenames (per `04_DATA_FORMATS.md`). Process
    docs should match.
  - **Considered and rejected:** UTC dating for the process docs
    (inconsistent with on-disk data conventions).
- **Decided:** macOS identity-strategy preference order in Phase 1 is
  `hardware_id` → `usb_port` → `index_fallback`, with each fallback
  required to record a warning.
  - **Why:** Spelled out in the spec's intent but never as an explicit
    ordering. Making it explicit prevents Phase 1 from silently picking
    `index_fallback` when `usb_port` was available.
  - **Considered and rejected:** Letting the OS helper choose freely
    (risk of silent regressions).

### 10. AI may push to GitHub, with per-action human approval

- **Decided:** Reverse the original "never push to GitHub" rule. AI
  sessions may run `git push` (and other remote-mutating commands like
  `gh pr create`) provided they ask for and receive explicit approval
  from the human in the same turn. Pushes to `main` are still
  prohibited — only phase branches get pushed; `main` advances on the
  remote only via a merged PR the human approves. Read-only `gh`
  commands do not require approval.
- **Why:** Now that the GitHub remote exists and SSH auth works
  silently from this machine, having the human run every `git push`
  by hand is friction without benefit. Per-action approval keeps the
  human in the loop on anything destructive or visible to others,
  while letting the AI close the "implement → commit → push" loop in
  one turn instead of stopping for a hand-off.
- **Considered and rejected:** Granting blanket push permission via
  the Claude Code allowlist (loses the per-action sanity check — a
  bad commit could ship before the human notices); keeping the
  original total ban (proven to be unnecessary friction now that
  auth is set up); letting the AI push to `main` directly with
  approval (still wrong — phase-branch-only is a separate invariant
  and shouldn't be relaxed at the same time).

### 11. Phase 3 web framework: Flask, not FastAPI

- **Decided:** The Phase 3 dashboard uses Flask. Pinned in
  `requirements.txt` at the time Phase 3 begins.
- **Why:** The dashboard is local, low-traffic, request/response only —
  no streaming, no websockets, no fan-out. Flask's smaller dependency
  tree (no Pydantic / Starlette / ASGI server) installs cleanly on the
  Windows lab machine. Synchronous Python composes naturally with the
  engine's threading model (scheduler thread + process-wide capture
  lock); FastAPI's async story would invite async/sync mixing bugs in
  code paths where the engine is firmly synchronous.
- **Considered and rejected:** FastAPI (extra deps, async/sync friction
  for zero benefit at this scale); deciding at Phase 3 start (the
  decision is already obvious from the constraints — no reason to
  defer).

### 12. Baseline-capture failure leaves the folder behind

- **Decided:** If the t=0 baseline capture fails after retries, the
  experiment folder and its `metadata.json` are kept, with
  `metadata.json` finalized as `end_reason="baseline_failed"`,
  `images_captured=0`, and `ended_at=<now>`. No entry is added to
  `running_state.json`. The `start_experiment` call returns failure to
  the caller.
- **Why:** Preserves the forensic record of the failed attempt — was
  the camera label wrong, the camera offline, the disk failing? The
  dashboard and future sessions can see "this station tried to start
  at HH:MM and failed" instead of silently pretending nothing happened.
- **Considered and rejected:** Deleting the folder (cleaner listing,
  but loses diagnostic value — and a crash mid-baseline would orphan
  anyway); leaving the folder but not finalizing `metadata.json`
  (creates "running"-looking entries on disk that aren't actually
  running, confusing later sessions).

### 13. macOS multi-camera identity uses index fallback in Phase 1

- **Decided:** On macOS, when more than one OpenCV camera index is
  detected, Phase 1 records `identity_strategy="index_fallback"` for
  each index instead of assigning hardware IDs from `system_profiler`.
- **Why:** Live testing showed `system_profiler` camera metadata order
  does not safely correlate to OpenCV AVFoundation index order. A
  wrong `hardware_id` assignment is more dangerous than an explicit
  weak mapping. The setup tool still captures previews so the operator
  can label the physical cameras, and warnings make the weakness loud.
- **Considered and rejected:** Pairing metadata rows to indexes by
  list position (observed to swap camera identities); omitting metadata
  warnings entirely (would hide the durability limitation from later
  phases).
