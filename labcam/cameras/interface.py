from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from labcam.cameras.base_capture import (
    capture_open_grab_close,
    macos_backend,
    save_jpeg_image,
    windows_backend,
)


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


def capture_frame(camera_id: int | str | CameraInfo) -> Any:
    with _CAPTURE_LOCK:
        camera = _resolve_camera(camera_id)
        return capture_open_grab_close(
            camera.index,
            backend=_backend_for_current_platform(),
        )


def preview_frame(camera_id: int | str | CameraInfo) -> Any:
    return capture_frame(camera_id)


def save_jpeg(image: Any, output_path: str | Path, *, quality: int | None = None) -> Path:
    return save_jpeg_image(image, Path(output_path), quality=quality)


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
