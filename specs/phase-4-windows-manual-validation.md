# Phase 4 Windows Manual Validation

Use this checklist on the Windows lab machine after cloning or pulling
the `phase-4-windows-verification` branch. Codex does not need to be
installed on Windows; paste the requested outputs back into the Mac
development session for review.

## Setup

Run from the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m compileall labcam tools
```

Paste back:
- Python version if virtualenv creation fails.
- Full install error if dependency installation fails.
- Full compile error if compilation fails.

## Camera Discovery

Run:

```powershell
.\.venv\Scripts\python tools\camera_setup.py list
```

Paste back the full output. Confirm whether all expected physical
cameras appear. If Windows exposes virtual or unwanted cameras, note
their indexes; later commands can use `--indexes` to limit the target
set after discovery.

## Camera Mapping

Run:

```powershell
.\.venv\Scripts\python tools\camera_setup.py setup
```

For each camera:
- Open the preview image path printed by the tool.
- Label the physical station (`station1`, `station2`, etc.).
- Add notes only when useful for physical placement.

Paste back:
- The final `config/cameras.json`.
- Any warnings printed during setup.
- Whether each preview matched the expected physical camera.

## Stress Test

Run all discovered target cameras, or use `--indexes` only if discovery
found unwanted devices:

```powershell
.\.venv\Scripts\python tools\camera_setup.py stress-test --cycles 100
```

Paste back the full output. Phase 4 expects 100/100 open-grab-close
captures per target camera.

## Dashboard Smoke Test

Run:

```powershell
.\.venv\Scripts\python -m labcam.main
```

Open `http://127.0.0.1:<port>` in the Windows browser. Validate:
- Preview each mapped camera.
- Start short experiments on all connected stations.
- Confirm each physical camera maps to the intended station.
- Confirm latest thumbnails update.
- Stop or let the runs finish.
- Confirm each experiment folder contains `metadata.json`,
  `capture_log.txt`, and `images/`.

Paste back:
- Any dashboard error messages.
- The names of generated experiment folders.
- One representative `metadata.json` and `capture_log.txt` if a
  dashboard run fails or maps the wrong camera.

## Full Phase 4 Record

Record pass/fail notes for every required scenario in `specs/phase-4.md`:
- Windows enumeration and mapping.
- 100-cycle stress test per target camera.
- Four concurrent camera experiments when four cameras are available.
- Identical-device disambiguation when matching webcams are available.
- Reboot survival.
- Same-port replug survival for `hardware_id` cameras.
- USB-port-move behavior for `usb_port` cameras, if any.
- One 4+ hour run.
- Framing/preview correctness on the real rig.
- Localhost and optional trusted-LAN dashboard access.
