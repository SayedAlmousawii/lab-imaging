#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
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
from labcam.engine.storage import build_metadata, create_experiment_paths, local_now, write_metadata
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
    root = Path(tempfile.mkdtemp(prefix="labcam-phase6-task4-")).resolve()
    scenarios: list[tuple[str, Callable[[Path], str]]] = [
        ("valid absolute path writes future experiment", scenario_valid_absolute_path),
        ("relative path resolves from project root", scenario_relative_path),
        ("missing directory is created", scenario_missing_directory_created),
        ("invalid storage paths rejected", scenario_invalid_storage_paths_rejected),
        ("active run keeps old folder", scenario_active_run_keeps_old_folder),
        ("restart loads saved location", scenario_restart_loads_saved_location),
        ("startup recovery uses stored folder", scenario_recovery_uses_stored_folder),
    ]

    print(f"Phase 6 Task 4 driver root={root}")
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

    passed = sum(1 for _, ok, _ in results if ok)
    print()
    print(f"Summary: {passed}/{len(results)} scenarios passed")
    for name, ok, detail in results:
        print(f"- {'PASS' if ok else 'FAIL'} {name}: {detail}")
    return 0 if passed == len(results) else 1


def scenario_valid_absolute_path(root: Path) -> str:
    config = _temp_config(root, "absolute", settings={"experiments_dir": str(root / "old")})
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    experiment_id: str | None = None
    try:
        _confirm_all(engine)
        destination = root / "absolute" / "new-output"
        response = client.post("/api/settings", json=_settings_payload(destination))
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Save failed: {response.status_code} {payload}")
        if engine.experiments_dir != destination.resolve():
            raise ScenarioFailure(f"Engine did not switch to new output: {engine.experiments_dir}")
        experiment_id = engine.start_experiment(_experiment_config("absolute-save", "station1"))
        if not (destination / experiment_id / "metadata.json").exists():
            raise ScenarioFailure("New experiment was not written to the selected folder")
        return "settings saved and future experiment used absolute folder"
    finally:
        if experiment_id:
            engine.stop_experiment(experiment_id)
        engine.shutdown_cleanly()


def scenario_relative_path(root: Path) -> str:
    relative = "tmp-phase6-task4-relative-output"
    destination = PROJECT_ROOT / relative
    if destination.exists():
        shutil.rmtree(destination)
    config = _temp_config(root, "relative", settings={})
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    experiment_id: str | None = None
    try:
        _confirm_all(engine)
        response = client.post("/api/settings", json=_settings_payload(relative))
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Relative save failed: {response.status_code} {payload}")
        saved = _read_json(config.settings_path)
        if saved["experiments_dir"] != relative:
            raise ScenarioFailure(f"Relative path was not preserved in settings: {saved}")
        if engine.experiments_dir != destination.resolve():
            raise ScenarioFailure(f"Relative path did not resolve from project root: {engine.experiments_dir}")
        experiment_id = engine.start_experiment(_experiment_config("relative-save", "station1"))
        if not (destination / experiment_id / "metadata.json").exists():
            raise ScenarioFailure("Relative output folder did not receive the experiment")
        return "relative path stored as entered and resolved from project root"
    finally:
        if experiment_id:
            engine.stop_experiment(experiment_id)
        engine.shutdown_cleanly()
        if destination.exists():
            shutil.rmtree(destination)


def scenario_missing_directory_created(root: Path) -> str:
    config = _temp_config(root, "create", settings={})
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        destination = root / "create" / "missing" / "nested"
        if destination.exists():
            shutil.rmtree(destination)
        response = client.post("/api/settings", json=_settings_payload(destination))
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Missing directory save failed: {response.status_code} {payload}")
        if not destination.is_dir():
            raise ScenarioFailure("Missing directory was not created")
        if list(destination.glob(".labcam-write-test-*")):
            raise ScenarioFailure("Write-test file was not cleaned up")
        return "missing directory was created, tested, and cleaned"
    finally:
        engine.shutdown_cleanly()


def scenario_invalid_storage_paths_rejected(root: Path) -> str:
    config = _temp_config(root, "invalid-paths", settings={"experiments_dir": str(root / "kept")})
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    readonly = root / "invalid-paths" / "readonly"
    try:
        file_path = root / "invalid-paths" / "not-a-directory.txt"
        file_path.write_text("not a folder\n", encoding="utf-8")
        before = config.settings_path.read_text(encoding="utf-8")
        file_response = client.post("/api/settings", json=_settings_payload(file_path))
        file_payload = file_response.get_json()
        after_file = config.settings_path.read_text(encoding="utf-8")
        if file_response.status_code != 400 or "experiments_dir" not in file_payload["error"].get("fields", {}):
            raise ScenarioFailure(f"File path was not rejected: {file_response.status_code} {file_payload}")
        if before != after_file:
            raise ScenarioFailure("File-path rejection modified settings")

        readonly.mkdir(parents=True)
        os.chmod(readonly, 0o555)
        read_response = client.post("/api/settings", json=_settings_payload(readonly))
        read_payload = read_response.get_json()
        after_readonly = config.settings_path.read_text(encoding="utf-8")
        if read_response.status_code != 400 or "experiments_dir" not in read_payload["error"].get("fields", {}):
            raise ScenarioFailure(f"Read-only path was not rejected: {read_response.status_code} {read_payload}")
        if before != after_readonly:
            raise ScenarioFailure("Read-only rejection modified settings")
        return "file and read-only destinations rejected without settings changes"
    finally:
        try:
            os.chmod(readonly, 0o755)
        except OSError:
            pass
        engine.shutdown_cleanly()


def scenario_active_run_keeps_old_folder(root: Path) -> str:
    old_dir = root / "active" / "old-output"
    new_dir = root / "active" / "new-output"
    config = _temp_config(root, "active", settings={"experiments_dir": str(old_dir)})
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    first_id: str | None = None
    second_id: str | None = None
    try:
        _confirm_all(engine)
        first_id = engine.start_experiment(_experiment_config("old-active", "station1"))
        response = client.post("/api/settings", json=_settings_payload(new_dir))
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Path-only active save failed: {response.status_code} {payload}")
        if not (old_dir / first_id / "metadata.json").exists():
            raise ScenarioFailure("Active experiment moved away from its original folder")
        second_id = engine.start_experiment(_experiment_config("new-future", "station2"))
        if not (new_dir / second_id / "metadata.json").exists():
            raise ScenarioFailure("Future experiment did not use the new folder")
        return "active run stayed in old folder and future run used new folder"
    finally:
        for experiment_id in (first_id, second_id):
            if experiment_id:
                engine.stop_experiment(experiment_id)
        engine.shutdown_cleanly()


def scenario_restart_loads_saved_location(root: Path) -> str:
    destination = root / "restart" / "saved-output"
    config = _temp_config(root, "restart", settings={"experiments_dir": str(destination)})
    engine = _engine(config)
    try:
        if engine.experiments_dir != destination.resolve():
            raise ScenarioFailure(f"Restart did not load saved folder: {engine.experiments_dir}")
        return "new engine loaded saved experiments_dir"
    finally:
        engine.shutdown_cleanly()


def scenario_recovery_uses_stored_folder(root: Path) -> str:
    old_dir = root / "recovery" / "old-output"
    new_dir = root / "recovery" / "new-output"
    config = _temp_config(root, "recovery", settings={"experiments_dir": str(new_dir)})
    started_at = local_now()
    paths = create_experiment_paths(
        experiments_dir=old_dir,
        experiment_name="recover-old-folder",
        camera_label="station1",
        started_at=started_at,
    )
    metadata = build_metadata(
        name="recover-old-folder",
        camera_label="station1",
        camera_id="hardware-0",
        camera_identity_strategy="hardware_id",
        interval_minutes=5,
        duration_hours=1,
        operator="",
        notes="",
        started_at=started_at,
        planned_stop_at=started_at,
        images_captured=1,
    )
    write_metadata(paths, metadata)
    config.state_path.write_text(
        json.dumps(
            {
                "running": [
                    {
                        "experiment_id": paths.experiment_id,
                        "experiment_folder": str(paths.root),
                        "camera_label": "station1",
                        "next_capture_at": started_at.isoformat(timespec="seconds"),
                        "planned_stop_at": started_at.isoformat(timespec="seconds"),
                        "images_captured": 1,
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    engine = _engine(config)
    try:
        recovered = _read_json(paths.metadata_path)
        if recovered["end_reason"] != "unknown":
            raise ScenarioFailure(f"Stored-folder recovery did not finalize metadata: {recovered}")
        if (_read_json(config.state_path)).get("running") != []:
            raise ScenarioFailure("Recovery did not clear running_state.json")
        return "startup recovery finalized experiment in stored old folder"
    finally:
        engine.shutdown_cleanly()


class _TempConfig:
    def __init__(self, root: Path, name: str, *, settings: dict[str, Any] | None) -> None:
        self.root = (root / name).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.root / "settings.json"
        self.cameras_path = self.root / "cameras.json"
        self.state_path = self.root / "running_state.json"
        if settings is not None:
            self.settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
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
                        },
                        {
                            "label": "station2",
                            "identity_strategy": "hardware_id",
                            "stable_id": "hardware-1",
                            "last_seen_index": 1,
                            "warnings": [],
                        },
                    ]
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def _temp_config(root: Path, name: str, *, settings: dict[str, Any] | None) -> _TempConfig:
    return _TempConfig(root, name, settings=settings)


def _engine(config: _TempConfig) -> CaptureEngine:
    return CaptureEngine(
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


def _settings_payload(experiments_dir: str | Path) -> dict[str, Any]:
    return {
        "experiments_dir": str(experiments_dir),
        "default_interval_minutes": "5",
        "default_duration_hours": "12",
        "jpeg_quality": "90",
        "capture_retries": "2",
        "warmup_frames": "5",
    }


def _experiment_config(name: str, camera_label: str) -> ExperimentConfig:
    return ExperimentConfig(
        name=name,
        camera_label=camera_label,
        interval_minutes=5,
        duration_hours=1,
    )


def _confirm_all(engine: CaptureEngine) -> None:
    status: dict[str, Any] | None = None
    for label in ("station1", "station2"):
        status = engine.confirm_camera(label)
    if status is None or status["required"]:
        raise ScenarioFailure(f"Stations were not confirmed: {status}")


def _detected_cameras() -> list[CameraInfo]:
    return [
        CameraInfo(
            label="USB Camera 0",
            identity_strategy="hardware_id",
            stable_id="hardware-0",
            index=0,
            warnings=[],
        ),
        CameraInfo(
            label="USB Camera 1",
            identity_strategy="hardware_id",
            stable_id="hardware-1",
            index=1,
            warnings=[],
        ),
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
