# Phase 7 - Portable Windows Packaging

This is the implementation spec for the first user-friendly packaging
unit. It turns the current source-run workflow into a portable Windows
folder that lab operators can copy, unzip, and run without Git, Python
setup, or developer commands.

Phase 7 must start only after Phase 6 is reviewed and either completed
or explicitly paused by the human.

## Goal

Ship Lab Imaging as a portable Windows folder for lab operators:

1. Copy or unzip the folder onto the lab computer.
2. Double-click `Start Lab Imaging.bat`.
3. The app starts locally and opens the dashboard in the default browser.
4. Runtime config, camera mappings, running state, logs, and experiment
   folders stay visible beside the app or in the configured save
   location.

This first package is intentionally not a formal installer. The package
should make daily use friendlier while preserving the current local-first
Flask dashboard and file-based experiment model.

## In Scope

- Build a Windows portable folder using PyInstaller one-folder mode.
- Add a packaged launcher entry point that starts the existing Flask app
  and opens the local dashboard in the default browser.
- Keep the existing developer entry point, `python -m labcam.main`,
  working unchanged for source runs.
- Include Flask templates, static assets, self-hosted fonts, and
  `config/settings.json.example` in the packaged output.
- Keep writable runtime files outside PyInstaller internals:
  `config/settings.json`, `config/cameras.json`,
  `config/running_state.json`, logs, and experiment output.
- Add a Windows build script that creates a distributable folder such as
  `dist/LabImagingPortable/`.
- Add operator-facing start-here documentation inside the portable
  folder.
- Validate the package on the Windows lab machine with real camera
  hardware before treating it as usable.

## Out of Scope

- No MSI, NSIS, Inno Setup, or other installer in this first packaging
  unit.
- No Windows service, system tray app, background autostart, or browser
  kiosk mode.
- No Electron wrapper.
- No code signing. Windows SmartScreen or unknown-publisher prompts are
  acceptable for this first internal package.
- No LAN/authentication changes.
- No camera-capture behavior changes, live-preview changes, or storage
  schema changes.
- No automatic cloud upload or direct cloud API integration.

## Package Shape

The build output should be a folder that can be zipped and copied:

```text
LabImagingPortable/
+-- LabImaging.exe
+-- Start Lab Imaging.bat
+-- README-START-HERE.txt
+-- config/
|   +-- settings.json.example
+-- experiments/
+-- logs/
+-- _internal/
```

The exact PyInstaller internal folder name may differ, but runtime files
must not be written into that internal bundle location.

## Implementation Notes

- Use PyInstaller one-folder mode, not one-file mode. One-folder mode is
  a better fit for Flask templates, static files, OpenCV binaries, and
  visible writable runtime data.
- Build the Windows package on Windows. PyInstaller does not
  cross-compile Windows binaries from macOS.
- Introduce a small runtime-path helper if needed so source runs use the
  repository root and packaged runs use the folder containing
  `LabImaging.exe` as the writable application root.
- The existing source tree paths may continue to use the repo root, but
  packaged runs must resolve these writable paths beside the executable:
  - `config/settings.json`
  - `config/cameras.json`
  - `config/running_state.json`
  - default `experiments/`
  - package logs, if added
- The packaged launcher should:
  - load or create settings from `config/settings.json.example`;
  - start the existing Flask app on the configured local port;
  - wait briefly for the server to answer;
  - open `http://127.0.0.1:<web_port>` in the default browser;
  - print clear messages if the port is busy or startup fails.
- `Start Lab Imaging.bat` should run `LabImaging.exe` from the portable
  folder and keep a visible console open for startup errors and clean
  shutdown.
- The dashboard remains the user interface. Do not add a native desktop
  UI in this phase.
- Keep `tools/camera_setup.py` as a developer fallback in source runs.
  The portable operator path should prefer the existing dashboard Cameras
  page for camera setup.

## Build Artifacts

Add build-only files rather than hand-built release output:

- A PyInstaller spec file that explicitly collects:
  - `labcam/web/templates/`
  - `labcam/web/static/`
  - `config/settings.json.example`
  - any required OpenCV/pywin32 runtime dependencies not found
    automatically.
- A Windows build script that:
  - creates or reuses a Python 3.11 virtual environment;
  - installs normal requirements plus PyInstaller;
  - runs PyInstaller;
  - assembles `LabImagingPortable/`;
  - copies `Start Lab Imaging.bat` and `README-START-HERE.txt`;
  - creates empty `config/`, `experiments/`, and `logs/` folders as
    needed.

Do not commit generated `dist/` output unless the human explicitly asks
for release artifacts to be stored in the repo.

## Test Scenarios

1. **Fresh portable launch:** copy the folder to a new location, run
   `Start Lab Imaging.bat`, and confirm the browser opens to the
   dashboard.
2. **No system Python:** run on the Windows lab machine without relying
   on `py` or `python` from PATH.
3. **Path with spaces:** run from a folder such as
   `C:\Users\Lab Staff\Desktop\Lab Imaging`.
4. **First-run settings:** confirm `config/settings.json` is created
   from the example and remains editable through Settings.
5. **No camera config:** confirm the dashboard routes to camera setup
   rather than crashing.
6. **Camera setup:** configure cameras from the dashboard, verify
   cameras, and confirm `config/cameras.json` is written beside the
   portable app.
7. **Experiment workflow:** start an experiment, stop it, add
   post-experiment notes, browse it, and confirm output folders contain
   images, `metadata.json`, `capture_log.txt`, and optional
   `post_notes.txt`.
8. **Configured save location:** choose a different experiment folder in
   Settings and confirm future experiments save there.
9. **Restart behavior:** close the app cleanly, restart it, and confirm
   settings and camera config persist.
10. **Startup failure clarity:** verify the package gives clear console
    messages for port-in-use, missing bundled assets, and camera access
    failures.

## Validation Commands

Run the existing source validations before packaging:

```powershell
.\.venv\Scripts\python -m compileall labcam tools
node --check labcam\web\static\status.js
node --check labcam\web\static\new.js
node --check labcam\web\static\settings.js
node --check labcam\web\static\cameras.js
node --check labcam\web\static\experiments.js
node --check labcam\web\static\experiment_detail.js
node --check labcam\web\static\experiment_notes.js
node --check labcam\web\static\verify.js
.\.venv\Scripts\python tools\phase5_driver.py
.\.venv\Scripts\python tools\phase6_task1_driver.py
.\.venv\Scripts\python tools\phase6_task2_driver.py
.\.venv\Scripts\python tools\phase6_task3_driver.py
.\.venv\Scripts\python tools\phase6_task4_driver.py
.\.venv\Scripts\python tools\phase6_task5_driver.py
.\.venv\Scripts\python tools\phase6_task6_driver.py
.\.venv\Scripts\python tools\phase6_task7_driver.py
.\.venv\Scripts\python tools\phase6_task8_driver.py
rg "import cv2|from cv2" -n labcam tools
rg "cv2\\.imshow" -n labcam tools
rg "^opencv-python($|[<=>])" -n requirements.txt
```

Expected invariant checks:

- The only OpenCV import is still `labcam/cameras/base_capture.py`.
- There are still no `cv2.imshow` calls.
- `requirements.txt` still uses `opencv-python-headless`, never plain
  `opencv-python`.

After packaging, run the packaged app itself and complete the test
scenarios above on the Windows lab machine with real cameras.

## Acceptance Criteria

- A lab operator can run Lab Imaging by double-clicking
  `Start Lab Imaging.bat`.
- The dashboard opens automatically in the default browser.
- The packaged app runs without a separately installed Python runtime.
- Runtime files are visible and writable outside the PyInstaller
  internal bundle.
- Camera setup, verification, experiment start/stop, notes, experiment
  browsing, settings, and maintenance-mode behavior still work.
- Existing capture invariants still hold.
- The package is documented well enough that a non-developer can start
  it and know where experiment output is saved.

## References

- PyInstaller spec files and data files:
  `https://pyinstaller.org/en/stable/spec-files.html`
- PyInstaller runtime path behavior:
  `https://pyinstaller.org/en/stable/runtime-information.html`
- PyInstaller operating mode:
  `https://www.pyinstaller.org/en/v5.13.2/operating-mode.html`
