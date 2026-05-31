from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2

from labcam.paths import DEFAULT_SETTINGS_PATH


DEFAULT_WARMUP_FRAMES = 5
DEFAULT_JPEG_QUALITY = 90
SETTINGS_PATH = DEFAULT_SETTINGS_PATH


class CameraCaptureError(RuntimeError):
    """Raised when a camera cannot produce a still frame."""


def load_capture_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}

    with SETTINGS_PATH.open("r", encoding="utf-8") as settings_file:
        data = json.load(settings_file)

    if not isinstance(data, dict):
        raise CameraCaptureError(f"Settings file is not a JSON object: {SETTINGS_PATH}")

    return data


def capture_open_grab_close(
    camera_index: int,
    *,
    warmup_frames: int | None = None,
    backend: int | None = None,
) -> Any:
    settings = load_capture_settings()
    resolved_warmup_frames = int(
        warmup_frames
        if warmup_frames is not None
        else settings.get("warmup_frames", DEFAULT_WARMUP_FRAMES)
    )

    capture = (
        cv2.VideoCapture(camera_index, backend)
        if backend is not None
        else cv2.VideoCapture(camera_index)
    )

    try:
        if not capture.isOpened():
            raise CameraCaptureError(f"Could not open camera index {camera_index}")

        for _ in range(max(0, resolved_warmup_frames)):
            capture.read()

        ok, frame = capture.read()
        if not ok or frame is None:
            raise CameraCaptureError(f"Could not read frame from camera index {camera_index}")

        return frame
    finally:
        capture.release()


def save_jpeg_image(image: Any, output_path: Path, *, quality: int | None = None) -> Path:
    settings = load_capture_settings()
    resolved_quality = int(
        quality if quality is not None else settings.get("jpeg_quality", DEFAULT_JPEG_QUALITY)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ok = cv2.imwrite(
        str(output_path),
        image,
        [cv2.IMWRITE_JPEG_QUALITY, max(1, min(100, resolved_quality))],
    )
    if not ok:
        raise CameraCaptureError(f"Could not write JPEG: {output_path}")

    return output_path.resolve()


def macos_backend() -> int:
    return cv2.CAP_AVFOUNDATION


def windows_backend() -> int:
    return cv2.CAP_DSHOW


def opencv_version() -> str:
    return str(cv2.__version__)
