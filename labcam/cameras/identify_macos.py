from __future__ import annotations

import json
import subprocess
from typing import Any

from labcam.cameras.base_capture import capture_open_grab_close, macos_backend
from labcam.cameras.interface import CameraInfo


MAX_CAMERA_INDEX = 10


def list_macos_cameras() -> list[CameraInfo]:
    metadata = _load_macos_camera_metadata()
    working_indexes = _find_working_indexes()

    if len(working_indexes) != 1:
        return [_index_fallback_camera(index, metadata) for index in working_indexes]

    cameras: list[CameraInfo] = []
    for position, index in enumerate(working_indexes):
        metadata_item = metadata[position] if position < len(metadata) else {}
        cameras.append(_camera_info_from_metadata(index, metadata_item))

    return cameras


def _find_working_indexes() -> list[int]:
    indexes: list[int] = []

    for index in range(MAX_CAMERA_INDEX):
        try:
            capture_open_grab_close(index, warmup_frames=0, backend=macos_backend())
        except Exception:
            continue
        indexes.append(index)

    return indexes


def _load_macos_camera_metadata() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for data_type in ("SPCameraDataType", "SPUSBDataType"):
        items.extend(_system_profiler_items(data_type))

    return [item for item in items if _looks_like_camera(item)]


def _system_profiler_items(data_type: str) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["system_profiler", data_type, "-json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    root_items = payload.get(data_type, [])
    if not isinstance(root_items, list):
        return []

    return list(_flatten_items(root_items))


def _flatten_items(items: list[Any]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        flattened.append(item)
        children = item.get("_items")
        if isinstance(children, list):
            flattened.extend(_flatten_items(children))

    return flattened


def _looks_like_camera(item: dict[str, Any]) -> bool:
    text = " ".join(str(value).lower() for value in item.values() if not isinstance(value, list))
    camera_terms = ("camera", "webcam", "facetime", "logitech", "c310", "uvc")

    return any(term in text for term in camera_terms)


def _camera_info_from_metadata(index: int, metadata: dict[str, Any]) -> CameraInfo:
    hardware_id = _first_present(
        metadata,
        (
            "serial_num",
            "serial_number",
            "device_serial_num",
            "spcamera_unique-id",
            "unique_id",
        ),
    )
    usb_port = _first_present(
        metadata,
        (
            "location_id",
            "locationID",
            "usb_location_id",
            "device_location",
        ),
    )
    label = str(metadata.get("_name") or metadata.get("name") or f"camera-{index}")

    if hardware_id:
        return CameraInfo(
            label=label,
            identity_strategy="hardware_id",
            stable_id=hardware_id,
            index=index,
            warnings=[],
        )

    if usb_port:
        return CameraInfo(
            label=label,
            identity_strategy="usb_port",
            stable_id=usb_port,
            index=index,
            warnings=[
                "topology-dependent identity - moving this camera to a different USB port will break the mapping"
            ],
        )

    return CameraInfo(
        label=label,
        identity_strategy="index_fallback",
        stable_id=str(index),
        index=index,
        warnings=[
            "index fallback - OpenCV index only; not durable across reboots or replugging"
        ],
    )


def _index_fallback_camera(index: int, metadata: list[dict[str, Any]]) -> CameraInfo:
    names = sorted(
        {
            str(item.get("_name") or item.get("name")).strip()
            for item in metadata
            if str(item.get("_name") or item.get("name") or "").strip()
        }
    )
    warning = (
        "index fallback - macOS camera metadata could not be safely correlated "
        "to OpenCV index; not durable across reboots or replugging"
    )
    if names:
        warning = f"{warning}; detected metadata names: {', '.join(names)}"

    return CameraInfo(
        label=f"camera-{index}",
        identity_strategy="index_fallback",
        stable_id=str(index),
        index=index,
        warnings=[warning],
    )


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    return None
