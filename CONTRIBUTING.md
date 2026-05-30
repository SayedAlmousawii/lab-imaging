# Contributing

Developer notes for Lab Imaging. The root `README.md` is the lab-staff
runbook.

## Setup

Requires Python 3.11.

```sh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Use `opencv-python-headless`, never plain `opencv-python`.

## Project Context

Read these before changing code:

1. `AGENTS.md`
2. `HANDOFF.md`
3. The current `specs/phase-N.md`
4. Any focused task spec named by the handoff

The core invariants are still-image capture, open-grab-close camera
access, one process-wide camera lock, file-based experiment output, and
all OpenCV or OS-specific camera behavior isolated under
`labcam/cameras/`.

## Running the App

After `config/cameras.json` exists:

```sh
python -m labcam.main
```

By default the dashboard binds to `127.0.0.1:5000`. `allow_lan_access`
is intentionally `false`; v1 has no authentication.

The dashboard uses Flask, Jinja templates, plain CSS, and vanilla
JavaScript. It has no frontend build step and no CDN dependency. Inter
and JetBrains Mono are self-hosted under `labcam/web/static/fonts/`
(SIL OFL 1.1; license at `labcam/web/static/fonts/OFL.txt`).

If `design_handoff_lab_imaging/` exists locally, it is a gitignored
Claude Design reference export only. It is not shipped runtime code.

## Validation

Useful local checks:

```sh
.venv/bin/python -m compileall labcam tools
node --check labcam/web/static/status.js
node --check labcam/web/static/new.js
rg "import cv2|from cv2" -n labcam tools
rg "cv2\\.imshow" -n labcam tools
rg "^opencv-python($|[<=>])" -n requirements.txt
.venv/bin/python tools/phase5_driver.py
```

The only expected `cv2` import is
`labcam/cameras/base_capture.py`. There should be no `cv2.imshow`
calls and no plain `opencv-python` dependency.

For Phase 4 Windows hardware validation, use
`specs/phase-4-windows-manual-validation.md` on the Windows lab
machine.

## Defaults

Current safe defaults live in `config/settings.json.example`:

- `allow_lan_access=false`
- `jpeg_quality=90`
- `capture_retries=2`
- `default_interval_minutes=5`
- `default_duration_hours=12`
- `warmup_frames=5`

Only change defaults when hardware evidence supports the change, and
record non-trivial default decisions in `DECISIONS.md`.
