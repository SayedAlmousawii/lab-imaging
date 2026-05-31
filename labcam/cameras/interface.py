from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from labcam.cameras.base_capture import (
    capture_open_grab_close,
    macos_backend,
    opencv_version,
    save_jpeg_image,
    windows_backend,
)
from labcam.paths import PROJECT_ROOT, is_frozen


IdentityStrategy = Literal["hardware_id", "usb_port", "index_fallback"]

_CAPTURE_LOCK = Lock()


@dataclass(frozen=True)
class CameraInfo:
    label: str
    identity_strategy: IdentityStrategy
    stable_id: str
    index: int
    warnings: list[str] = field(default_factory=list)


def list_cameras() -> list[CameraInfo]:
    system_name = platform.system()

    if system_name == "Darwin":
        from labcam.cameras.identify_macos import list_macos_cameras

        return list_macos_cameras()

    if system_name == "Windows":
        from labcam.cameras.identify_windows import list_windows_cameras

        return list_windows_cameras()

    raise NotImplementedError(
        f"Camera enumeration for {system_name or 'this OS'} is not implemented"
    )


def list_cameras_fresh_process(*, timeout_seconds: float = 30) -> list[CameraInfo]:
    result = subprocess.run(
        _probe_command(),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Camera detection failed").strip()
        raise RuntimeError(detail)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Camera detection returned invalid data.") from exc

    records = payload.get("cameras") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise RuntimeError("Camera detection returned no camera list.")
    return [camera_info_from_dict(record) for record in records if isinstance(record, dict)]


def preview_camera_fresh_process(
    camera_index: int,
    output_path: str | Path,
    *,
    quality: int | None = None,
    timeout_seconds: float = 30,
) -> Path:
    command = _probe_command("--preview-index", str(camera_index), "--output", str(output_path))
    if quality is not None:
        command.extend(["--quality", str(quality)])

    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "Preview capture failed").strip()
        raise RuntimeError(detail)

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Preview capture returned invalid data.") from exc

    preview_path = payload.get("preview_path") if isinstance(payload, dict) else None
    if not preview_path:
        raise RuntimeError("Preview capture returned no output path.")
    return Path(str(preview_path))


def camera_info_to_dict(camera: CameraInfo) -> dict[str, object]:
    return {
        "label": camera.label,
        "identity_strategy": camera.identity_strategy,
        "stable_id": camera.stable_id,
        "index": camera.index,
        "warnings": camera.warnings,
    }


def camera_info_from_dict(record: dict[str, object]) -> CameraInfo:
    return CameraInfo(
        label=str(record["label"]),
        identity_strategy=str(record["identity_strategy"]),  # type: ignore[arg-type]
        stable_id=str(record["stable_id"]),
        index=int(record["index"]),
        warnings=list(record.get("warnings") or []),
    )


def capture_frame(camera_id: int | str | CameraInfo) -> Any:
    with _CAPTURE_LOCK:
        camera = _resolve_camera(camera_id)
        return capture_open_grab_close(
            camera.index,
            backend=_backend_for_current_platform(),
        )


def preview_frame(camera_id: int | str | CameraInfo) -> Any:
    return capture_frame(camera_id)


def check_camera_available(camera_id: int | str | CameraInfo) -> None:
    capture_frame(camera_id)


def save_jpeg(image: Any, output_path: str | Path, *, quality: int | None = None) -> Path:
    return save_jpeg_image(image, Path(output_path), quality=quality)


def get_opencv_version() -> str:
    return opencv_version()


def _resolve_camera(camera_id: int | str | CameraInfo) -> CameraInfo:
    if isinstance(camera_id, CameraInfo):
        if camera_id.identity_strategy != "index_fallback":
            for camera in list_cameras():
                if (
                    camera.identity_strategy == camera_id.identity_strategy
                    and camera.stable_id == camera_id.stable_id
                ):
                    return CameraInfo(
                        label=camera_id.label,
                        identity_strategy=camera.identity_strategy,
                        stable_id=camera.stable_id,
                        index=camera.index,
                        warnings=camera.warnings,
                    )
            raise ValueError(
                f"Configured camera {camera_id.label!r} with "
                f"{camera_id.identity_strategy}={camera_id.stable_id!r} was not detected"
            )
        return camera_id

    if isinstance(camera_id, int):
        return CameraInfo(
            label=f"camera-{camera_id}",
            identity_strategy="index_fallback",
            stable_id=str(camera_id),
            index=camera_id,
            warnings=[
                "index fallback - OpenCV index only; not durable across reboots or replugging"
            ],
        )

    if camera_id.isdigit():
        return _resolve_camera(int(camera_id))

    for camera in list_cameras():
        if camera.stable_id == camera_id or camera.label == camera_id:
            return camera

    raise ValueError(f"Unknown camera id: {camera_id}")


def _backend_for_current_platform() -> int | None:
    system_name = platform.system()
    if system_name == "Darwin":
        return macos_backend()
    if system_name == "Windows":
        return windows_backend()

    return None


def _probe_command(*args: str) -> list[str]:
    if is_frozen():
        return [sys.executable, "--camera-probe", *args]
    return [sys.executable, "-m", "labcam.cameras.probe", *args]
