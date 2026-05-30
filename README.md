# Lab Imaging

Lab Imaging captures periodic still images from lab cameras during a
time-bounded experiment. It does not record video. Each run creates a
folder with timestamped JPEG images, `metadata.json`, and
`capture_log.txt` so the results can be copied and read without special
software.

The v1 system is designed for one Windows lab computer with USB cameras
connected locally.

## Daily Use

1. Start the lab computer and connect the cameras.
2. Open PowerShell in the Lab Imaging folder.
3. Start the dashboard:

```powershell
.\.venv\Scripts\python -m labcam.main
```

4. Open the dashboard URL printed in PowerShell. By default it is:

```text
http://127.0.0.1:5000
```

5. Select **New experiment**.
6. Select the station camera and press **Preview**. Preview is a fresh
   still image, not a live stream.
7. Enter the experiment name, interval, duration, operator, and notes.
8. Press **Start experiment**.
9. Leave the dashboard open on **Station status** while the run is
   active.
10. Use **Stop** only if the run should end early.

The app automatically stops a run when its duration is reached.

## Finding Results

By default, experiment folders are saved under:

```text
experiments\
```

The save location can be changed from **Settings**. Changes apply only
to future experiments; existing experiment folders stay where they were
created.

Each folder is named with the date, experiment name, and camera label.
Inside the folder:

- `images\` contains timestamped `.jpg` still images.
- `metadata.json` records the run settings and stop reason.
- `capture_log.txt` records start, capture, error, and stop events.

To copy data off the lab computer, wait until the experiment is stopped,
then copy the whole experiment folder. Do not move or rename an active
run folder while the app is capturing.

## Camera Setup

If the dashboard says `config/cameras.json` is missing, run camera setup
before starting the dashboard:

```powershell
.\.venv\Scripts\python tools\camera_setup.py list
.\.venv\Scripts\python tools\camera_setup.py setup
```

Use the preview images from setup to label each physical camera. If the
computer exposes extra virtual or phone cameras, setup can target known
indexes:

```powershell
.\.venv\Scripts\python tools\camera_setup.py setup --indexes 0 1
```

The current Windows lab setup may use `index_fallback` camera identity.
That is safe to run, but it is weaker than hardware identity. After
replugging cameras or rebooting the computer, always use Preview before
starting a long experiment.

## Dashboard Messages

**Camera unavailable** means the app cannot open the configured camera.
Check the USB cable, replug the camera, and verify with Preview.

**Capture warning** means one or two scheduled still captures failed.
The experiment keeps running and records a sequence gap if a capture is
fully missed.

**Station needs attention** means repeated scheduled captures are
failing. Check the camera connection. The experiment keeps running until
its planned stop or until you stop it.

**Storage is full** or **Storage is not writable** means the affected
experiment stopped because it could not save results. Free disk space or
check the results folder, then start a new run.

**Camera identity uses fallback mapping** means the camera label is tied
to the current OpenCV index. Verify Preview after camera changes.

## If the App Will Not Start

- Confirm PowerShell is open in the Lab Imaging folder.
- Confirm the virtual environment exists at `.venv`.
- If `config/cameras.json` is missing, run camera setup.
- If port `5000` is already in use, ask the developer before changing
  settings.
- If camera access fails after replugging or rebooting, run Preview or
  camera setup again.

## Cloud Sync and Backups

The app writes local files only and does not need internet access during
capture. If the lab uses OneDrive, Google Drive Desktop, Dropbox, or a
network backup tool, choose a normal local folder managed by that tool
from **Settings**. Capture should always write to local storage first.

## When to Call the Developer

Call the developer if:

- the dashboard will not start after camera setup;
- the same camera repeatedly shows unavailable after replugging;
- storage errors continue after freeing disk space;
- experiment folders are missing `metadata.json` or `capture_log.txt`;
- the lab needs new workflow features such as settings screens,
  experiment browsing, post-run notes, live preview, or auto-resume.

## V1 Limits

Lab Imaging v1 does not auto-resume after a crash or reboot. It does
not analyze images automatically, combine multiple lab computers, trigger
captures from events, or provide authenticated LAN access. Those are
future extensions, not required steps for daily v1 operation.
