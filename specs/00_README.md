# Lab Imaging System — Planning Docs

This folder is the design spec for a laboratory imaging system. It is written to
be handed to **Claude Code** (or any developer) to build the project.

## Read these in order

1. **`01_PROJECT_OVERVIEW.md`** — the problem, the goal, what's in/out of scope.
2. **`02_ARCHITECTURE.md`** — high-level design, locked-in decisions, tech stack,
   the cross-platform strategy.
3. **`03_PROJECT_STRUCTURE.md`** — directory layout, modules, responsibilities,
   dependency direction.
4. **`04_DATA_FORMATS.md`** — exact on-disk formats (folders, filenames, JSON, logs).
5. **`05_BUILD_PLAN.md`** — phased roadmap and build order.

## The one-paragraph summary

Replace phone-based long-duration video recording of lab experiments with a
Python system on a central computer that captures **periodic still images** from
**USB webcams** at fixed intervals (5–10 min). Each experiment is duration-bounded,
auto-stops, and produces a **self-contained folder** of timestamped images plus
metadata and a log. Measurements (oil/water level against a physical ruler) are
read **manually** from the images later — no computer vision in v1. A **local web
dashboard** lets lab staff choose a camera, name an experiment, request a fresh
preview snapshot, set interval/duration, and start/stop/monitor runs. **No
hosting, no database.** Built with **Python 3.11 + opencv-python-headless + a
local Flask/FastAPI server**.

## Non-negotiable design rules (for whoever builds it)

- **Stills, not video.** Open-grab-close per capture; close the camera every time.
- **Stagger captures** — never two cameras open simultaneously.
- **Isolate all OS/OpenCV code in `labcam/cameras/`.** Nothing above it branches
  on OS or imports OpenCV. This is the entire cross-platform strategy.
- **Preview is a fresh still, not a stream.** Preview uses the same
  open-grab-close capture path as scheduled captures.
- **Files, not a database.** The experiment folder is the dataset.
- **One failed scheduled capture never kills an already-running experiment** —
  log, retry, continue. The initial `t=0` baseline capture is different: if it
  fails after retries, the experiment start fails.
- **One experiment per camera in v1.** A camera/station cannot run two active
  experiments at the same time.
- **Develop on macOS; the lab runs Windows.** A real Windows hardware test pass
  (Phase 4) is mandatory before go-live.
- **v1 crash behavior = accept loss (Option A).** No auto-resume yet, but keep the
  design friendly to adding it later.

## Build first

Start with **Phase 1: the camera test & labeling tool** (`tools/camera_setup.py`)
so the hardware and camera identity/labeling approach are proven before anything
is built on top of them.
