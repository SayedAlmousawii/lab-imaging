# Project Structure & Module Layout

## Directory Layout

```
labcam/
├── README.md                  # Setup + run instructions
├── requirements.txt           # Python dependencies
├── config/
│   ├── cameras.json           # Camera label + identity mapping (created by setup)
│   └── settings.json          # App settings (port, paths, defaults)
│
├── labcam/                    # The application package
│   ├── __init__.py
│   │
│   ├── cameras/               # === THE OS-SPECIFIC BOX ===
│   │   ├── __init__.py
│   │   ├── interface.py       # Abstract interface: list_cameras(), capture_frame()
│   │   ├── base_capture.py    # OpenCV open-grab-close logic (shared, OS-agnostic)
│   │   ├── identify_macos.py  # macOS camera enumeration / identity strategy (dev)
│   │   └── identify_windows.py# Windows camera enumeration / identity strategy (lab)
│   │
│   ├── engine/                # === CAPTURE ENGINE (headless, no UI) ===
│   │   ├── __init__.py
│   │   ├── experiment.py      # Experiment model: config, state, lifecycle
│   │   ├── scheduler.py       # The loop: who's due, stagger, capture, finalize
│   │   ├── storage.py         # Folder creation, filenames, metadata, logging
│   │   └── state.py           # Tracks currently-running experiments (state file)
│   │
│   ├── web/                   # === LOCAL DASHBOARD ===
│   │   ├── __init__.py
│   │   ├── server.py          # Flask/FastAPI app; routes; talks to engine
│   │   ├── static/            # CSS, JS
│   │   └── templates/         # HTML (status view, new-experiment panel)
│   │
│   └── main.py                # Entry point: starts engine + web server
│
├── tools/
│   └── camera_setup.py        # Standalone: list cameras, preview, save labels/identity
│
└── experiments/               # OUTPUT — created at runtime (see data format)
    └── <date>_<name>_<camera>/
        ├── metadata.json
        ├── capture_log.txt
        └── images/
```

## Module Responsibilities

### `cameras/` — the only OS-aware code
The isolation boundary for the cross-platform strategy. Nothing outside this
package should import OpenCV or do any OS branching.

- **`interface.py`** — defines the contract the rest of the app depends on:
  - `list_cameras() -> list[CameraInfo]` (label, identity strategy, identity
    value, index, warnings)
  - `capture_frame(camera_id) -> image` (one frame, via open-grab-close)
  - `preview_frame(camera_id) -> image` (one fresh still for the dashboard)
- **`base_capture.py`** — the OpenCV open-grab-close routine (open → discard
  warm-up frames → grab → return; caller saves). OS-agnostic.
- **`identify_macos.py` / `identify_windows.py`** — provide camera identity
  information for each OS. Each camera reports whether matching is based on a
  `hardware_id`, `usb_port`, or `index_fallback`. Selected at runtime by
  detecting the platform. This is the ~20 lines of branching that constitute the
  entire cross-platform effort.

### `engine/` — capture logic, no UI
- **`experiment.py`** — represents one experiment: its config (name, camera,
  interval, duration, operator, notes), computed stop time, and runtime state
  (images captured, next-due time, status: idle/capturing/finished/stopped).
- **`scheduler.py`** — the heart. A loop that periodically checks all running
  experiments, finds which are due for a capture, performs **staggered**
  open-grab-close captures through the process-wide global capture lock (never
  two cameras open at once), writes images, finalizes experiments whose duration
  has elapsed, and logs everything. One failed scheduled capture logs an error,
  records a sequence gap if retries are exhausted, and continues. A failed `t=0`
  baseline capture fails experiment start.
- **`storage.py`** — creates experiment folders, generates sortable timestamped
  filenames, writes `metadata.json`, appends to `capture_log.txt`.
- **`state.py`** — reads/writes the small "currently running" state file so the
  dashboard knows what's live and the program has a single source of truth.

### `web/` — the dashboard
- **`server.py`** — local HTTP server. Exposes routes the UI calls:
  - list cameras (with labels)
  - get a fresh preview snapshot from a chosen camera
  - create/start an experiment
  - stop an experiment early
  - get current status of all experiments/stations
  - get the latest captured frame for a running experiment
- **`templates/` + `static/`** — the UI: a status table and a new-experiment
  panel with a button-triggered preview snapshot. Plain HTML/CSS/JS; keep it
  simple.

### `tools/camera_setup.py` — first thing you run
Standalone utility to: enumerate cameras, create a preview snapshot for each,
collect labels and optional notes, and save a `config/cameras.json` mapping
physical cameras to labels plus identity metadata. It must use only
`labcam/cameras/` APIs; it must not import `cv2` directly. Everything else
depends on these labels existing.

### `main.py` — entry point
Loads config, starts the capture engine (scheduler thread), starts the web
server, opens the dashboard. One command to run the whole system.

## Dependency Direction (important)

```
web/  ──►  engine/  ──►  cameras/
                  └──►  storage (files on disk)
```

- `web` depends on `engine`; `engine` depends on `cameras`.
- **Nothing** depends on `web` (you could run the engine headless).
- **Only** `cameras/` knows about OpenCV and the OS. Keep it that way.
