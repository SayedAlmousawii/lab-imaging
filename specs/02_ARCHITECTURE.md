# Architecture & Design Decisions

## High-Level Architecture

A **single Python program** running on the lab computer that does two things:

1. **Capture Engine** — a scheduler that performs periodic image capture. Knows
   nothing about the UI. Can run headless.
2. **Local Web Dashboard** — a local HTTP server + browser UI that talks to the
   engine to configure, start, monitor, and stop experiments.

All data is stored as **plain files and folders on disk**. No database.

```
                 ┌─────────────────────────────────────────┐
                 │            Lab Computer (Windows)         │
                 │                                           │
   Browser  ◄────┤  Local Web Dashboard (Flask/FastAPI)      │
 (localhost      │        │                                  │
  or LAN IP)     │        ▼                                  │
                 │  Capture Engine (scheduler)               │
                 │        │                                  │
                 │        ▼                                  │
                 │  Camera Layer (OpenCV + OS helper)        │
                 │        │                                  │
                 │   ┌────┴────┬────────┬────────┐           │
                 │  cam0     cam1     cam2     cam3          │
                 │                                           │
                 │  Disk:  experiments/<folders>/            │
                 └─────────────────────────────────────────┘
```

## Core Design Decisions (Locked In)

### 1. Periodic stills, not video
Capture one frame every N minutes. Interval is configurable per experiment.
Default interval: **5–10 minutes**.

### 2. Open-Grab-Close capture strategy
For each capture, per camera:
1. Open the camera.
2. Discard the first few frames (let auto-exposure settle).
3. Grab one frame.
4. Save it as JPEG.
5. **Close the camera.**

**Why:** the camera is active only ~2–3s out of every 300–600s. This means:
- USB bandwidth contention effectively disappears.
- No overheating.
- Captures can be **staggered** so no two cameras are open simultaneously.
- The "4 USB camera limit" is a *continuous-streaming* limit and does **not**
  apply here — the system can likely exceed 4 cameras.

The small per-capture warm-up delay is irrelevant at 5–10 minute intervals.

### 3. Experiment is the unit of organization
- A **station** = a camera.
- An **experiment** = a duration-bounded capture job on one camera, with its own
  name, interval, duration, and output folder.
- Multiple experiments run **concurrently and independently**. Starting/stopping
  one does not affect others.
- In v1, a camera/station may have **only one active experiment** at a time.
- User flow: choose camera → name it → set interval + duration → preview →
  **Start**. System captures until duration elapses, then **auto-stops** and
  finalizes the folder.
- Capture a baseline frame at **t=0** (immediately on start), then every interval.
  If the baseline capture fails after configured retries, the experiment start
  fails and no running experiment is created.

### 4. Crash/reboot behavior: Option A (accept loss) for v1
If the program crashes or the machine reboots mid-experiment, the captured images
so far are kept; the experiment is considered over. **No auto-resume in v1.**
(Auto-resume — detecting an experiment that should still be running and continuing
for the remaining time — is a documented future extension.)

On startup, if `config/running_state.json` contains experiments from a prior
process, the program marks each experiment's metadata with
`ended_at=<startup time>` and `end_reason="unknown"`, then clears
`running_state.json`. It does not resume them.

### 5. Storage = files and folders, no database
The per-experiment folder *is* the dataset. Benefits: inspectable, portable,
no dependencies, anyone can browse images and read metadata without special tools.
The only "live state" tracked is which experiments are currently running, held in
a single small state file the program reads on startup and updates on change.
`metadata.json` and `running_state.json` must be written atomically
(temporary file + fsync + rename). The append-only `capture_log.txt` does not
need atomic rewrite behavior.

### 6. Local-only dashboard (no hosting)
The dashboard is a local HTTP server. Access via `http://localhost:<port>` on the
lab machine. Optionally reachable from another machine on the same LAN via the
host's local IP (nice-to-have, no extra hosting). Nothing leaves the network.

## Cross-Platform Strategy

**Develop on macOS, deploy on Windows.** This is NOT "support two user
populations forever" — it's "write once, run on the Windows lab machines."

- Python + OpenCV + browser dashboard run on both OSes **with no special work**.
- The **only** genuinely OS-specific concern is the camera layer: how cameras are
  enumerated/identified, plus occasional exposure/format quirks.
- **Strategy:** isolate ALL camera access behind one small module with a clean
  interface (e.g. `list_cameras()`, `capture_frame(camera_id)`). Provide a macOS
  implementation (for dev) and a Windows implementation (for the lab) behind the
  same interface. Everything above it (engine, dashboard) is OS-agnostic and never
  knows which OS it's on.
- OpenCV backends: **AVFoundation** on macOS, **DirectShow** on Windows.
- **Mandatory:** one real test pass on an actual Windows lab machine with the
  actual webcams before go-live. This is verification, not parallel development.

## Camera Identification (the OS-specific risk)

OpenCV's camera **enumeration is weak** — it gives index numbers (0,1,2,3) that
are **not durable** across reboots/replugging. For an unattended multi-station
system this is dangerous: "station 1" could silently become a different camera.

**Solution:** a one-time setup/labeling step that maps each physical camera to a
human label ("Station 1", "Station 2", ...) and records the identity strategy
used to match it later. The label mapping is saved to `config/cameras.json` and
reused.

Use these terms exactly in code, comments, log messages, and user-facing text:

- **stable identity** — a true durable hardware identifier, such as a serial
  number or OS instance ID.
- **topology-dependent identity** — a USB port path. It is valid only while the
  physical USB topology is unchanged.
- **index fallback** — an OpenCV index only. It is not durable across
  reboots/replugging.

Phase 1 must discover the best available identity strategy on macOS. If no
durable hardware identifier is available, continue with topology-dependent
identity or index fallback, but warn loudly. Code that consumes `cameras.json`
must respect `identity_strategy` when deciding how confident a camera match is.

## Technology Stack

| Concern              | Choice                          | Notes |
|----------------------|---------------------------------|-------|
| Language             | Python 3.11                     | Runs on Mac + Windows |
| Camera capture       | OpenCV (`opencv-python-headless`)| Open-grab-close; no `cv2.imshow` dependency |
| Camera identification| OS-specific helper module       | Identity strategy + labels; the one OS-divergent piece |
| Web backend          | Flask **or** FastAPI            | Local server; pick one and stay simple |
| Dashboard front-end  | HTML/CSS/JS in browser          | Fresh preview snapshot, status table, forms |
| Scheduling           | In-process scheduler/threads    | Wake on interval, staggered captures with one global capture lock |
| Storage              | Filesystem (folders + JSON + log)| No database |
| Image format         | JPEG                            | Good size/quality for manual reading |

All captures, including preview snapshots and scheduled captures, must pass
through a single process-wide capture lock. This is the enforcement mechanism for
"never two cameras open simultaneously," even if scheduler work uses threads.

Preview is always a button-triggered fresh still produced via open-grab-close.
There is no streaming preview in v1.

## Image Quality Considerations (capture-setup guidance, not code)

These are physical-setup notes the software can't fix but the build should respect:
- **Fixed camera + ruler rig** per station — must not move during/between runs.
- **Consistent, diffuse lighting**; avoid glare on the liquid/ruler and changing
  daylight over a 20-hour run. This is the biggest "garbage in" risk for manual
  reading.
- **Frame tight** on the liquid column + ruler so resolution is spent where it
  matters. v1 captures at the camera's default resolution and does not expose
  focus, exposure, or rotation controls. JPEG quality defaults to 90.
- The **Preview** feature exists precisely to catch framing/glare/focus problems
  before committing to a long run.
