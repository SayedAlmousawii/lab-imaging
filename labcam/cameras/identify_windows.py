from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from labcam.cameras.base_capture import capture_open_grab_close, windows_backend
from labcam.cameras.interface import CameraInfo


MAX_CAMERA_INDEX = 10


@dataclass(frozen=True)
class _DirectShowDevice:
    name: str
    display_name: str


def list_windows_cameras() -> list[CameraInfo]:
    devices = _directshow_devices()
    working_indexes = _find_working_indexes()

    if not working_indexes:
        return []

    if len(devices) != len(working_indexes):
        return [_index_fallback_camera(index, devices) for index in working_indexes]

    cameras: list[CameraInfo] = []
    for index, device in zip(working_indexes, devices):
        cameras.append(_camera_info_from_device(index, device))
    return cameras


def _find_working_indexes() -> list[int]:
    indexes: list[int] = []

    for index in range(MAX_CAMERA_INDEX):
        try:
            capture_open_grab_close(index, warmup_frames=0, backend=windows_backend())
        except Exception:
            continue
        indexes.append(index)

    return indexes


def _directshow_devices() -> list[_DirectShowDevice]:
    try:
        import pythoncom  # type: ignore[import-not-found]
        import win32com.client  # type: ignore[import-not-found]
    except ImportError:
        return []

    devices: list[_DirectShowDevice] = []
    pythoncom.CoInitialize()
    try:
        enumerator = win32com.client.Dispatch("SystemDeviceEnum")
        category = _video_input_device_category()
        monikers = enumerator.CreateClassEnumerator(category, 0)
        if not monikers:
            return []

        while True:
            chunk = monikers.Next(1)
            if not chunk:
                break
            moniker = chunk[0]
            name = _friendly_name(moniker) or "Windows camera"
            display_name = _display_name(moniker)
            devices.append(_DirectShowDevice(name=name, display_name=display_name))
    except Exception:
        return []
    finally:
        pythoncom.CoUninitialize()

    return devices


def _video_input_device_category() -> Any:
    try:
        import pythoncom  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for DirectShow enumeration") from exc

    return pythoncom.MakeIID("{860BB310-5D01-11D0-BD3B-00A0C911CE86}")


def _friendly_name(moniker: Any) -> str | None:
    try:
        bag = moniker.BindToStorage(None, None, _property_bag_iid())
        value = bag.Read("FriendlyName")
    except Exception:
        return None

    if isinstance(value, tuple) and value:
        value = value[0]
    return str(value).strip() or None


def _property_bag_iid() -> Any:
    try:
        import pythoncom  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("pywin32 is required for DirectShow enumeration") from exc

    return pythoncom.MakeIID("{55272A00-42CB-11CE-8135-00AA004BB851}")


def _display_name(moniker: Any) -> str:
    try:
        return str(moniker.GetDisplayName(None, None)).strip()
    except Exception:
        return ""


def _camera_info_from_device(index: int, device: _DirectShowDevice) -> CameraInfo:
    hardware_id = _hardware_id_from_display_name(device.display_name)
    if hardware_id:
        return CameraInfo(
            label=device.name or f"camera-{index}",
            identity_strategy="hardware_id",
            stable_id=hardware_id,
            index=index,
            warnings=[],
        )

    usb_port = _usb_port_from_display_name(device.display_name)
    if usb_port:
        return CameraInfo(
            label=device.name or f"camera-{index}",
            identity_strategy="usb_port",
            stable_id=usb_port,
            index=index,
            warnings=[
                "topology-dependent identity - moving this camera to a different USB port will break the mapping"
            ],
        )

    return _index_fallback_camera(index, [device])


def _hardware_id_from_display_name(display_name: str) -> str | None:
    normalized = _normalize_display_name(display_name)
    if "usb#vid_" not in normalized and "vid_" not in normalized:
        return None

    match = re.search(r"(?:@device:pnp:)?\\\\\?\\(.+?)(?:#\{|\{)", normalized)
    if match:
        return match.group(1).strip("#\\") or None

    match = re.search(r"(usb#vid_[^{}]+)", normalized)
    if match:
        return match.group(1).strip("#\\") or None

    return normalized or None


def _usb_port_from_display_name(display_name: str) -> str | None:
    normalized = _normalize_display_name(display_name)
    match = re.search(r"(usb#[^{}]+)", normalized)
    if not match:
        return None

    return match.group(1).strip("#\\") or None


def _normalize_display_name(display_name: str) -> str:
    return display_name.strip().lower().replace("/", "\\")


def _index_fallback_camera(index: int, devices: list[_DirectShowDevice]) -> CameraInfo:
    names = sorted({device.name for device in devices if device.name.strip()})
    warning = (
        "index fallback - Windows DirectShow metadata could not be safely correlated "
        "to OpenCV index; not durable across reboots or replugging"
    )
    if names:
        warning = f"{warning}; detected DirectShow names: {', '.join(names)}"

    return CameraInfo(
        label=f"camera-{index}",
        identity_strategy="index_fallback",
        stable_id=str(index),
        index=index,
        warnings=[warning],
    )
