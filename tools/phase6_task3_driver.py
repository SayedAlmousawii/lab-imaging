#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labcam.cameras.interface import CameraInfo
from labcam.engine import CaptureEngine, ExperimentConfig
from labcam.web.server import create_app


ONE_PIXEL_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/"
    "xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/"
    "xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Al//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEA"
    "AgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z"
)


class ScenarioFailure(RuntimeError):
    pass


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="labcam-phase6-task3-")).resolve()
    scenarios: list[tuple[str, Callable[[Path], str]]] = [
        ("settings page renders", scenario_settings_page_renders),
        ("settings API merges defaults", scenario_settings_api_merges_defaults),
        ("valid save persists", scenario_valid_save_persists),
        ("invalid save rejected", scenario_invalid_save_rejected),
        ("missing settings created", scenario_missing_settings_created),
        ("active experiment blocks save", scenario_active_experiment_blocks_save),
    ]

    print(f"Phase 6 Task 3 driver root={root}")
    results: list[tuple[str, bool, str]] = []
    for name, run in scenarios:
        try:
            detail = run(root)
        except Exception as exc:
            results.append((name, False, str(exc)))
            print(f"FAIL {name}: {exc}")
        else:
            results.append((name, True, detail))
            print(f"PASS {name}: {detail}")

    passed = sum(1 for _, ok, _ in results)
    print()
    print(f"Summary: {passed}/{len(results)} scenarios passed")
    for name, ok, detail in results:
        print(f"- {'PASS' if ok else 'FAIL'} {name}: {detail}")
    return 0 if passed == len(results) else 1


def scenario_settings_page_renders(root: Path) -> str:
    config = _temp_config(root, "page", with_camera_config=False, settings={})
    engine = _engine(root, "page", config=config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.get("/settings")
        if response.status_code != 200:
            raise ScenarioFailure(f"Settings page failed: {response.status_code}")
        if b"settings.js" not in response.data or b'href="/settings"' not in response.data:
            raise ScenarioFailure("Settings page did not include script and nav link")
        return "settings page and navigation rendered"
    finally:
        engine.shutdown_cleanly()


def scenario_settings_api_merges_defaults(root: Path) -> str:
    config = _temp_config(
        root,
        "merge",
        with_camera_config=False,
        settings={"default_interval_minutes": 9, "custom_flag": "kept"},
    )
    engine = _engine(root, "merge", config=config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.get("/api/settings")
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Settings API failed: {response.status_code} {payload}")
        settings = payload["settings"]
        diagnostics = payload["diagnostics"]
        if settings["default_interval_minutes"] != 9 or settings["default_duration_hours"] != 12:
            raise ScenarioFailure(f"Defaults were not merged: {settings}")
        if settings["custom_flag"] != "kept":
            raise ScenarioFailure(f"Unknown setting was not preserved in payload: {settings}")
        if diagnostics["settings_path"] != str(config.settings_path):
            raise ScenarioFailure(f"Diagnostics path mismatch: {diagnostics}")
        if not diagnostics["python_version"] or not diagnostics["opencv_version"]:
            raise ScenarioFailure(f"Diagnostics missing versions: {diagnostics}")
        return "defaults, custom keys, and diagnostics returned"
    finally:
        engine.shutdown_cleanly()


def scenario_valid_save_persists(root: Path) -> str:
    config = _temp_config(
        root,
        "valid",
        with_camera_config=True,
        settings={"allow_lan_access": True, "custom_key": "preserve-me"},
    )
    engine = _engine(root, "valid", config=config)
    app = create_app(engine)
    client = app.test_client()
    try:
        _confirm_station(engine)
        response = client.post(
            "/api/settings",
            json={
                "default_interval_minutes": "7.5",
                "default_duration_hours": "3",
                "jpeg_quality": "88",
                "capture_retries": "4",
                "warmup_frames": "6",
            },
        )
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Valid save failed: {response.status_code} {payload}")
        saved = _read_json(config.settings_path)
        if saved["custom_key"] != "preserve-me" or saved["allow_lan_access"] is not True:
            raise ScenarioFailure(f"Read-only or custom settings were not preserved: {saved}")
        if saved["default_interval_minutes"] != 7.5 or saved["jpeg_quality"] != 88:
            raise ScenarioFailure(f"Editable settings were not saved: {saved}")
        if engine.settings["default_interval_minutes"] != 7.5 or engine.jpeg_quality != 88:
            raise ScenarioFailure("Engine settings were not refreshed after save")
        new_page = client.get("/new")
        if new_page.status_code != 200 or b'value="7.5"' not in new_page.data:
            raise ScenarioFailure(f"New experiment defaults not refreshed: {new_page.status_code}")
        return "settings saved, preserved, and reflected on /new"
    finally:
        engine.shutdown_cleanly()


def scenario_invalid_save_rejected(root: Path) -> str:
    original = {
        "default_interval_minutes": 5,
        "default_duration_hours": 12,
        "jpeg_quality": 90,
        "capture_retries": 2,
        "warmup_frames": 5,
    }
    config = _temp_config(root, "invalid", with_camera_config=False, settings=original)
    engine = _engine(root, "invalid", config=config)
    app = create_app(engine)
    client = app.test_client()
    try:
        before = config.settings_path.read_text(encoding="utf-8")
        response = client.post(
            "/api/settings",
            json={
                "default_interval_minutes": "0",
                "default_duration_hours": "-1",
                "jpeg_quality": "101",
                "capture_retries": "2.5",
                "warmup_frames": "-1",
            },
        )
        payload = response.get_json()
        after = config.settings_path.read_text(encoding="utf-8")
        if response.status_code != 400 or payload["error"]["code"] != "invalid_settings":
            raise ScenarioFailure(f"Invalid save was not rejected: {response.status_code} {payload}")
        if set(payload["error"].get("fields", {})) != {
            "default_interval_minutes",
            "default_duration_hours",
            "jpeg_quality",
            "capture_retries",
            "warmup_frames",
        }:
            raise ScenarioFailure(f"Field errors missing: {payload}")
        if before != after:
            raise ScenarioFailure("Invalid save modified settings file")
        return "invalid numeric settings rejected without file changes"
    finally:
        engine.shutdown_cleanly()


def scenario_missing_settings_created(root: Path) -> str:
    config = _temp_config(root, "missing", with_camera_config=False, settings=None)
    engine = _engine(root, "missing", config=config)
    app = create_app(engine)
    client = app.test_client()
    try:
        if config.settings_path.exists():
            raise ScenarioFailure("Missing settings scenario started with a settings file")
        response = client.get("/api/settings")
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Missing settings load failed: {response.status_code} {payload}")
        if not config.settings_path.exists():
            raise ScenarioFailure("Settings file was not created")
        saved = _read_json(config.settings_path)
        if saved["default_interval_minutes"] != 5 or payload["settings"]["jpeg_quality"] != 90:
            raise ScenarioFailure(f"Defaults were not created: {saved}")
        return "settings.json created from example defaults"
    finally:
        engine.shutdown_cleanly()


def scenario_active_experiment_blocks_save(root: Path) -> str:
    config = _temp_config(root, "active", with_camera_config=True, settings={})
    engine = _engine(root, "active", config=config)
    app = create_app(engine)
    client = app.test_client()
    experiment_id: str | None = None
    try:
        _confirm_station(engine)
        before = config.settings_path.read_text(encoding="utf-8")
        experiment_id = engine.start_experiment(
            ExperimentConfig(
                name="active-settings-block",
                camera_label="station1",
                interval_minutes=5,
                duration_hours=1,
            )
        )
        response = client.post(
            "/api/settings",
            json={
                "default_interval_minutes": "2",
                "default_duration_hours": "4",
                "jpeg_quality": "75",
                "capture_retries": "1",
                "warmup_frames": "1",
            },
        )
        payload = response.get_json()
        after = config.settings_path.read_text(encoding="utf-8")
        if response.status_code != 409 or payload["error"]["code"] != "settings_busy":
            raise ScenarioFailure(f"Active save was not blocked: {response.status_code} {payload}")
        if before != after:
            raise ScenarioFailure("Active save modified settings file")
        return "running experiment blocked settings save"
    finally:
        if experiment_id:
            engine.stop_experiment(experiment_id)
        engine.shutdown_cleanly()


class _TempConfig:
    def __init__(
        self,
        root: Path,
        name: str,
        *,
        with_camera_config: bool,
        settings: dict[str, Any] | None,
    ) -> None:
        self.root = (root / name).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.root / "settings.json"
        self.cameras_path = self.root / "cameras.json"
        self.state_path = self.root / "running_state.json"
        if settings is not None:
            self.settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        if with_camera_config:
            self.cameras_path.write_text(
                json.dumps(
                    {
                        "cameras": [
                            {
                                "label": "station1",
                                "identity_strategy": "hardware_id",
                                "stable_id": "hardware-0",
                                "last_seen_index": 0,
                                "warnings": [],
                            }
                        ]
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )


def _temp_config(
    root: Path,
    name: str,
    *,
    with_camera_config: bool,
    settings: dict[str, Any] | None,
) -> _TempConfig:
    return _TempConfig(root, name, with_camera_config=with_camera_config, settings=settings)


def _engine(root: Path, name: str, *, config: _TempConfig) -> CaptureEngine:
    return CaptureEngine(
        experiments_dir=root / name / "experiments",
        settings_path=config.settings_path,
        cameras_path=config.cameras_path,
        state_path=config.state_path,
        capture_func=_capture_ok,
        preview_func=_capture_ok,
        camera_check_func=_camera_check_ok,
        detected_camera_func=_detected_cameras,
        detected_preview_func=_preview_detected_ok,
        save_jpeg_func=_save_jpeg,
        disk_usage_func=_disk_usage,
        poll_floor_seconds=0.05,
    )


def _confirm_station(engine: CaptureEngine) -> None:
    status = engine.confirm_camera("station1")
    if status["required"]:
        raise ScenarioFailure(f"Station was not confirmed: {status}")


def _detected_cameras() -> list[CameraInfo]:
    return [
        CameraInfo(
            label="USB Camera 0",
            identity_strategy="hardware_id",
            stable_id="hardware-0",
            index=0,
            warnings=[],
        )
    ]


def _capture_ok(_: CameraInfo) -> bytes:
    return ONE_PIXEL_JPEG


def _camera_check_ok(_: CameraInfo) -> None:
    return None


def _preview_detected_ok(camera_index: int, output_path: Path, *, quality: int | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(ONE_PIXEL_JPEG)
    return output_path.resolve()


def _save_jpeg(image: Any, output_path: Path, *, quality: int | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image if isinstance(image, bytes) else ONE_PIXEL_JPEG)
    return output_path.resolve()


def _disk_usage(_: Path) -> shutil._ntuple_diskusage:
    return shutil._ntuple_diskusage(total=30_000_000_000, used=1_000_000_000, free=29_000_000_000)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
