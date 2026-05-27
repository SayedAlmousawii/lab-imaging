# AGENTS.md — Persistent Rulebook

Every AI session working on this repository **must read this file first**,
then `HANDOFF.md`, then `specs/phase-N.md` for the current phase, before
taking any action. This file contains **invariants only** — never status.
Status lives in `HANDOFF.md`. Decisions are logged in `DECISIONS.md`.

If a rule in this file conflicts with something a user message asks for in
the moment, surface the conflict and ask — do not silently override.

---

## Project purpose

A laboratory imaging system that captures periodic still images from USB
webcams on a central lab computer, replacing unreliable phone-based long-
duration video. Each experiment is duration-bounded, auto-stops, and
produces a self-contained folder of timestamped images plus metadata and
a log, all readable by lab staff without special tools.

## Non-negotiable design rules

These come from `specs/00_README.md` and are the load-bearing constraints
of the whole system. Violating any of them breaks something important.

- **Stills, not video.** Open-grab-close per capture. The camera is
  closed between captures.
- **Stagger captures — never two cameras open simultaneously.** Enforced
  via a single process-wide capture lock that **every** capture path
  (preview, baseline, scheduled) routes through.
- **Isolate all OS / OpenCV code in `labcam/cameras/`.** Nothing above
  that package branches on OS or imports OpenCV. This is the entire
  cross-platform strategy.
- **Preview is a fresh still, not a stream.** Preview uses the same
  open-grab-close path as scheduled captures.
- **Files, not a database.** The experiment folder is the dataset.
  `metadata.json` and `running_state.json` are written atomically
  (temporary file + fsync + rename). `capture_log.txt` is append-only.
- **One failed scheduled capture never kills an already-running
  experiment** — log, retry, record a sequence gap on total failure,
  continue. The **t=0 baseline** capture is the exception: if it fails
  after retries, the experiment start fails.
- **One experiment per camera in v1.** A station cannot run two active
  experiments at the same time.
- **Develop on macOS; the lab runs Windows.** A real Windows hardware
  test pass (Phase 4) is mandatory before go-live.
- **v1 crash behavior = accept loss (Option A).** No auto-resume.

## Directory map

```
/
├── AGENTS.md           ← this file (invariants, read first)
├── HANDOFF.md          ← live status (read second, update last)
├── DECISIONS.md        ← append-only decisions log
├── specs/
│   ├── 00_README.md            ← spec entry point
│   ├── 01_PROJECT_OVERVIEW.md
│   ├── 02_ARCHITECTURE.md
│   ├── 03_PROJECT_STRUCTURE.md
│   ├── 04_DATA_FORMATS.md
│   ├── 05_BUILD_PLAN.md
│   └── phase-N.md              ← authoritative spec for current phase
├── labcam/             ← application package (created in Phase 0+)
├── tools/              ← standalone utilities (Phase 1+)
├── config/             ← runtime config (most files gitignored)
└── experiments/        ← runtime output (gitignored)
```

### Reading order for a new session

1. `AGENTS.md` (this file).
2. `HANDOFF.md` — current state of the project.
3. `specs/phase-N.md` for the phase named as current in HANDOFF.md.
4. Specific specs (`02_ARCHITECTURE.md`, `04_DATA_FORMATS.md`, etc.)
   only when the task requires them.

## Workflow rules

- **Work only on the current phase branch.** Never commit to `main`.
  The current branch is named in `HANDOFF.md`.
- **Ask before pushing to GitHub.** Local commits are free; `git push`,
  `git push --force`, branch deletes on the remote, tag pushes, and any
  `gh` command that mutates the remote (PR create/merge/close, release
  create, etc.) all require an explicit per-action approval from the
  human in the current turn. Read-only `gh` calls (`gh pr view`,
  `gh run list`, etc.) do not require approval. Never push to `main`
  directly; only phase branches get pushed, and `main` advances on the
  remote only via a merged PR the human approves.
- **Never implement future phases early. Never skip ahead** in the
  build plan. If you find yourself needing a future-phase capability,
  stop and ask.
- **Ask when ambiguous; do not guess.** A clarifying question costs
  far less than the wrong implementation.
- **Update `HANDOFF.md` as the last action of every session**, even
  if nothing changed — in that case write a dated entry explicitly
  stating "no changes this session".
- **Append to `DECISIONS.md`** whenever a non-trivial decision is
  made. Dated entry, three fields: **Decided** / **Why** /
  **Considered and rejected**.

## Tooling rules

- **Python 3.11.**
- **`opencv-python-headless`**, never plain `opencv-python`. No GUI
  dependencies.
- **No `cv2.imshow`** anywhere. Ever. Headless preview means writing
  JPEGs to disk and printing paths.
- **No `import cv2` outside `labcam/cameras/`.** That package is the
  only OS-aware / OpenCV-aware box.
- Web framework: Flask or FastAPI — whichever Phase 3 lands on. No
  other web frameworks, no front-end framework.

## Dated-entry convention

Entries in `HANDOFF.md` and `DECISIONS.md` are grouped under date
headings of the form `## YYYY-MM-DD — short title`. Use the local lab
date (the human's local date) — not UTC.
