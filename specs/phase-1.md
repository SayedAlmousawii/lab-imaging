# Phase 1 — Camera Test & Labeling Tool

This is the authoritative spec for Phase 1 work. It pulls the Phase 1 section
of `05_BUILD_PLAN.md` together with all Phase 1-relevant clarifications from
`02_ARCHITECTURE.md` and `03_PROJECT_STRUCTURE.md`. If anything in the broader
specs contradicts this file for Phase 1 scope, this file wins for Phase 1.

## Goal

Prove the actual webcams work on the dev machine, and establish a durable
mapping from physical cameras to human-friendly labels with explicit
identity-strategy metadata. Phase 1 produces the foundation everything else
is built on.

## Deliverables

1. `tools/camera_setup.py` — a standalone CLI utility that:
   - Enumerates available cameras via the `labcam/cameras/` interface.
   - For each detected camera, captures a **button-triggered fresh preview
     snapshot** (open-grab-close), saves it to the OS temp directory
     (`tempfile.gettempdir()`), and prints the absolute path so the operator
     can open it manually. **Do not write previews into `experiments/`. Do
     not use `cv2.imshow` or any GUI call.**
   - Lets the operator assign a free-form **sanitized** label (alphanumeric
     + hyphens; no spaces or slashes; `station1`, `station2`, ... suggested)
     and optional notes per camera.
   - Records, per camera: `identity_strategy`, `stable_id`, `last_seen_index`,
     and `warnings` (empty array when none).
   - Saves the mapping to `config/cameras.json` (format per
     `specs/04_DATA_FORMATS.md`).
   - Must use **only `labcam/cameras/` APIs**. Must **not** import `cv2`
     directly.

2. `labcam/cameras/interface.py` — the abstract contract:
   - `list_cameras() -> list[CameraInfo]` returning label, identity
     strategy, identity value, index, warnings.
   - `capture_frame(camera_id) -> image` — one frame via open-grab-close.
   - `preview_frame(camera_id) -> image` — one fresh still for the
     dashboard / setup tool (same path as `capture_frame` in v1).

3. `labcam/cameras/base_capture.py` — the OS-agnostic OpenCV
   open-grab-close routine: open → discard warm-up frames (count from
   `settings.json`, default 5) → grab → return; caller saves. This is the
   **only** module that imports `cv2` in Phase 1.

4. `labcam/cameras/identify_macos.py` — macOS camera enumeration and
   identity-strategy discovery. Phase 1 must determine the best identity
   strategy available on macOS (AVFoundation). If no durable hardware
   identifier is available, fall back to `usb_port`, then `index_fallback`,
   **and emit a loud warning** captured in the camera's `warnings` array.

## Identity strategy — terminology (use these exact terms in code, log
messages, comments, and any user-facing text)

- **stable identity** (`identity_strategy: "hardware_id"`) — a true durable
  hardware identifier (serial number, OS instance ID).
- **topology-dependent identity** (`identity_strategy: "usb_port"`) — a USB
  port path. Valid only while physical USB topology is unchanged. Moving
  the camera to a different port breaks the mapping.
- **index fallback** (`identity_strategy: "index_fallback"`) — an OpenCV
  index only. Not durable across reboots/replugging. Use only when
  nothing better is available, and warn.

Code that consumes `cameras.json` later (Phase 2+) must respect
`identity_strategy` when deciding how confident a camera match is.

## Capture rules (Phase 1)

- **Open-grab-close** every capture. Never hold a camera open between
  captures, even in the setup tool.
- **Never two cameras open simultaneously.** Phase 1 enforces this via a
  single process-wide capture lock in `labcam/cameras/`. All preview and
  capture calls go through this lock — no exceptions.
- **JPEG quality default = 90.** Capture at the camera's **default
  resolution**. Phase 1 does not expose focus, exposure, or rotation
  controls.
- **Backend:** AVFoundation on macOS (set via OpenCV `cv2.CAP_AVFOUNDATION`).
  Do not branch on OS anywhere outside `labcam/cameras/`.

## Testing (Phase 1)

- Available hardware: built-in Mac camera + at least one Logitech C310
  USB webcam.
- **Repeated open-grab-close stress test before any unplug/replug work:**
  **100 capture cycles per camera**, no failures. This is a hard gate.
- After the stress test passes, exercise unplug/replug and re-enumeration
  to confirm the recorded identity strategy behaves as documented for
  whichever strategy ended up selected.
- **Identical-device validation is deferred to Phase 4 (Windows hardware
  pass)** — a second identical webcam is not available on the Mac dev
  machine, so identical-Logitech-C310 disambiguation is verified later.

## Out of scope for Phase 1

- The capture engine (scheduler, experiment lifecycle, storage) — Phase 2.
- The web dashboard — Phase 3.
- Windows identification (`identify_windows.py`) — Phase 4.
- Any automatic measurement / CV — out of v1 entirely.
- Streaming preview — never in v1; preview is always a fresh still.

## Definition of done

- You can run `python tools/camera_setup.py`, see every connected webcam
  listed, request and open a fresh preview snapshot for each, assign a
  sanitized label and optional notes, and the resulting `config/cameras.json`
  matches the schema in `specs/04_DATA_FORMATS.md` with a correct
  `identity_strategy` for each camera.
- The 100-cycle open-grab-close stress test passes on every connected
  camera without errors.
- Nothing outside `labcam/cameras/` imports `cv2` or branches on OS.
- The mapping survives at least one process restart on the same hardware
  in the same configuration.
