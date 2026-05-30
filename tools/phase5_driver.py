#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labcam.cameras.interface import CameraInfo
from labcam.engine import CaptureEngine, ExperimentConfig
from labcam.engine.state import RunningStateManager
from labcam.engine.storage import (
    append_log_line,
    atomic_write_json,
    build_metadata,
    create_experiment_paths,
    local_now,
    read_json_file,
)
from labcam.web.server import _station_status


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
    parser = argparse.ArgumentParser(description="Exercise Phase 5 hardening scenarios.")
    parser.add_argument("--experiments-dir", type=Path)
    args = parser.parse_args()

    experiments_dir = (
        args.experiments_dir.resolve()
        if args.experiments_dir
        else Path(tempfile.mkdtemp(prefix="labcam-phase5-driver-")).resolve()
    )
    results: list[tuple[str, bool, str]] = []
    scenarios: list[tuple[str, Callable[[], str]]] = [
        ("normal health", lambda: scenario_normal_health(experiments_dir)),
        ("single capture failure", lambda: scenario_single_capture_failure(experiments_dir)),
        ("capture failing threshold", lambda: scenario_capture_failing_threshold(experiments_dir)),
        ("capture recovery", lambda: scenario_capture_recovery(experiments_dir)),
        ("idle configured camera unavailable", lambda: scenario_idle_camera_unavailable(experiments_dir)),
        ("camera unavailable", lambda: scenario_camera_unavailable(experiments_dir)),
        ("camera failure is not disk failure", lambda: scenario_camera_failure_not_disk(experiments_dir)),
        ("unclear save failure is not disk failure", lambda: scenario_unclear_save_failure_not_disk(experiments_dir)),
        ("image write storage failure", lambda: scenario_storage_failed(experiments_dir)),
        ("low-space storage failure", lambda: scenario_disk_full(experiments_dir)),
        ("clean shutdown one run", lambda: scenario_clean_shutdown_one(experiments_dir)),
        ("clean shutdown two runs", lambda: scenario_clean_shutdown_two(experiments_dir)),
        ("shutdown during capture", lambda: scenario_shutdown_during_capture(experiments_dir)),
        ("clean shutdown waits for long capture", lambda: scenario_shutdown_waits_for_long_capture(experiments_dir)),
        ("crash recovery unchanged", lambda: scenario_crash_recovery(experiments_dir)),
    ]

    print(f"Phase 5 driver experiments_dir={experiments_dir}")
    for name, run in scenarios:
        try:
            detail = run()
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


def scenario_normal_health(experiments_dir: Path) -> str:
    with _temp_config("health-ok") as config:
        engine = _engine(experiments_dir, config, capture_func=_capture_ok)
        try:
            experiment_id = _start(engine, "health-ok", "phase5-health-ok")
            station = _station(engine, "health-ok")
            if station["health_state"] != "ok" or station["state"] != "running":
                raise ScenarioFailure(f"unexpected station health: {station}")
            return experiment_id
        finally:
            engine.shutdown_cleanly()


def scenario_single_capture_failure(experiments_dir: Path) -> str:
    with _temp_config("single-failure") as config:
        failures = _ScheduledFailures([True])
        engine = _engine(experiments_dir, config, capture_func=failures.capture)
        try:
            experiment_id = _start(engine, "single-failure", "phase5-single-failure")
            _wait_for(lambda: _experiment(engine, experiment_id)["consecutive_failures"] == 1)
            experiment = _experiment(engine, experiment_id)
            if experiment["health_state"] != "capture_warning":
                raise ScenarioFailure(f"expected capture_warning, got {experiment['health_state']}")
            _assert_not_terminal_storage(experiment)
            return experiment_id
        finally:
            engine.shutdown_cleanly()


def scenario_capture_failing_threshold(experiments_dir: Path) -> str:
    with _temp_config("threshold") as config:
        failures = _ScheduledFailures([True, True, True])
        engine = _engine(experiments_dir, config, capture_func=failures.capture)
        try:
            experiment_id = _start(engine, "threshold", "phase5-threshold")
            _wait_for(lambda: _experiment(engine, experiment_id)["consecutive_failures"] >= 3)
            station = _station(engine, "threshold")
            if station["health_state"] != "capture_failing" or station["state"] != "error":
                raise ScenarioFailure(f"expected dashboard error state, got {station}")
            return experiment_id
        finally:
            engine.shutdown_cleanly()


def scenario_capture_recovery(experiments_dir: Path) -> str:
    with _temp_config("recovery") as config:
        failures = _ScheduledFailures([True, True, True, False])
        engine = _engine(experiments_dir, config, capture_func=failures.capture)
        try:
            experiment_id = _start(engine, "recovery", "phase5-recovery")
            _wait_for(lambda: _experiment(engine, experiment_id)["consecutive_failures"] >= 3)
            _wait_for(lambda: _experiment(engine, experiment_id)["consecutive_failures"] == 0, timeout=8)
            station = _station(engine, "recovery")
            if station["health_state"] != "ok" or station["state"] != "running":
                raise ScenarioFailure(f"expected recovered ok station, got {station}")
            return experiment_id
        finally:
            engine.shutdown_cleanly()


def scenario_camera_unavailable(experiments_dir: Path) -> str:
    with _temp_config("unavailable") as config:
        failures = _ScheduledFailures(["unavailable"])
        engine = _engine(experiments_dir, config, capture_func=failures.capture)
        try:
            experiment_id = _start(engine, "unavailable", "phase5-unavailable")
            _wait_for(lambda: _station(engine, "unavailable")["health_state"] == "camera_unavailable")
            station = _station(engine, "unavailable")
            if station["state"] != "offline":
                raise ScenarioFailure(f"expected offline station, got {station}")
            return experiment_id
        finally:
            engine.shutdown_cleanly()


def scenario_idle_camera_unavailable(experiments_dir: Path) -> str:
    with _temp_config("idle-unavailable") as config:
        def unavailable(_: CameraInfo) -> None:
            raise RuntimeError("Could not open camera index 99")

        engine = _engine(experiments_dir, config, camera_check_func=unavailable)
        try:
            station = _station(engine, "idle-unavailable")
            if station["health_state"] != "camera_unavailable" or station["state"] != "offline":
                raise ScenarioFailure(f"expected idle offline station, got {station}")
            return station["camera_label"]
        finally:
            engine.shutdown_cleanly()


def scenario_camera_failure_not_disk(experiments_dir: Path) -> str:
    with _temp_config("camera-not-disk") as config:
        failures = _ScheduledFailures([True])
        engine = _engine(experiments_dir, config, capture_func=failures.capture)
        try:
            experiment_id = _start(engine, "camera-not-disk", "phase5-camera-not-disk")
            _wait_for(lambda: _experiment(engine, experiment_id)["consecutive_failures"] == 1)
            experiment = _experiment(engine, experiment_id)
            _assert_not_terminal_storage(experiment)
            return experiment_id
        finally:
            engine.shutdown_cleanly()


def scenario_unclear_save_failure_not_disk(experiments_dir: Path) -> str:
    with _temp_config("unclear-save") as config:
        save = _ScheduledSaveFailure(RuntimeError("jpeg encoder rejected frame"))
        engine = _engine(experiments_dir, config, save_jpeg_func=save.save)
        try:
            experiment_id = _start(engine, "unclear-save", "phase5-unclear-save")
            _wait_for(lambda: _experiment(engine, experiment_id)["consecutive_failures"] == 1)
            experiment = _experiment(engine, experiment_id)
            _assert_not_terminal_storage(experiment)
            if experiment.get("status") != "capturing":
                raise ScenarioFailure(f"unclear save failure stopped experiment: {experiment}")
            return experiment_id
        finally:
            engine.shutdown_cleanly()


def scenario_storage_failed(experiments_dir: Path) -> str:
    with _temp_config("storage-failed") as config:
        save = _ScheduledSaveFailure(OSError("permission denied"))
        engine = _engine(experiments_dir, config, save_jpeg_func=save.save)
        try:
            experiment_id = _start(engine, "storage-failed", "phase5-storage-failed")
            _wait_for(
                lambda: _finished(engine, experiment_id).get("end_reason") == "storage_failed"
                and _state_is_empty(config.state_path)
            )
            _assert_state_empty(config.state_path)
            return experiment_id
        finally:
            engine.shutdown()


def scenario_disk_full(experiments_dir: Path) -> str:
    with _temp_config("disk-full") as config:
        save = _ScheduledSaveFailure(OSError("write failed"))
        usage_calls = 0

        def disk_usage(_: Path) -> shutil._ntuple_diskusage:
            nonlocal usage_calls
            usage_calls += 1
            if usage_calls == 1:
                return shutil._ntuple_diskusage(total=30_000_000_000, used=1, free=25_000_000_000)
            return shutil._ntuple_diskusage(total=10_000, used=10_000, free=0)

        engine = _engine(experiments_dir, config, save_jpeg_func=save.save, disk_usage_func=disk_usage)
        try:
            experiment_id = _start(engine, "disk-full", "phase5-disk-full")
            _wait_for(
                lambda: _finished(engine, experiment_id).get("end_reason") == "disk_full"
                and _state_is_empty(config.state_path)
            )
            _assert_state_empty(config.state_path)
            return experiment_id
        finally:
            engine.shutdown()


def scenario_clean_shutdown_one(experiments_dir: Path) -> str:
    with _temp_config("shutdown-one") as config:
        engine = _engine(experiments_dir, config)
        experiment_id = _start(engine, "shutdown-one", "phase5-shutdown-one")
        engine.shutdown_cleanly()
        _assert_end_reason(experiments_dir / experiment_id, "stopped_early")
        _assert_state_empty(config.state_path)
        return experiment_id


def scenario_clean_shutdown_two(experiments_dir: Path) -> str:
    with _temp_config("shutdown-a", "shutdown-b") as config:
        engine = _engine(experiments_dir, config)
        first = _start(engine, "shutdown-a", "phase5-shutdown-a")
        second = _start(engine, "shutdown-b", "phase5-shutdown-b")
        engine.shutdown_cleanly()
        _assert_end_reason(experiments_dir / first, "stopped_early")
        _assert_end_reason(experiments_dir / second, "stopped_early")
        _assert_state_empty(config.state_path)
        return f"{first}, {second}"


def scenario_shutdown_during_capture(experiments_dir: Path) -> str:
    with _temp_config("slow-capture") as config:
        entered = threading.Event()
        release = threading.Event()
        calls = 0

        def capture(camera: CameraInfo) -> Any:
            nonlocal calls
            calls += 1
            if calls > 1:
                entered.set()
                release.wait(timeout=5)
            return ONE_PIXEL_JPEG

        engine = _engine(experiments_dir, config, capture_func=capture)
        experiment_id = _start(engine, "slow-capture", "phase5-slow-shutdown")
        _wait_for(lambda: entered.is_set(), timeout=5)
        thread = threading.Thread(target=engine.shutdown_cleanly)
        thread.start()
        time.sleep(0.2)
        release.set()
        thread.join(timeout=6)
        if thread.is_alive():
            raise ScenarioFailure("shutdown did not finish after slow capture released")
        _assert_end_reason(experiments_dir / experiment_id, "stopped_early")
        _assert_state_empty(config.state_path)
        return experiment_id


def scenario_shutdown_waits_for_long_capture(experiments_dir: Path) -> str:
    with _temp_config("long-capture") as config:
        entered = threading.Event()
        release = threading.Event()
        calls = 0

        def capture(camera: CameraInfo) -> Any:
            nonlocal calls
            calls += 1
            if calls > 1:
                entered.set()
                release.wait(timeout=8)
            return ONE_PIXEL_JPEG

        engine = _engine(experiments_dir, config, capture_func=capture)
        experiment_id = _start(engine, "long-capture", "phase5-long-shutdown")
        _wait_for(lambda: entered.is_set(), timeout=5)
        thread = threading.Thread(target=engine.shutdown_cleanly)
        thread.start()
        time.sleep(5.2)
        if not thread.is_alive():
            raise ScenarioFailure("clean shutdown finalized before long capture finished")
        metadata = read_json_file(experiments_dir / experiment_id / "metadata.json")
        if metadata.get("end_reason") is not None:
            raise ScenarioFailure(f"metadata finalized before capture finished: {metadata}")
        release.set()
        thread.join(timeout=4)
        if thread.is_alive():
            raise ScenarioFailure("shutdown did not finish after long capture released")
        _assert_end_reason(experiments_dir / experiment_id, "stopped_early")
        _assert_state_empty(config.state_path)
        return experiment_id


def scenario_crash_recovery(experiments_dir: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="labcam-phase5-recovery-") as temp:
        temp_path = Path(temp)
        state_path = temp_path / "running_state.json"
        started_at = local_now()
        paths = create_experiment_paths(
            experiments_dir=experiments_dir,
            experiment_name="phase5-crash-recovery",
            camera_label="station-recovery",
            started_at=started_at,
        )
        metadata = build_metadata(
            name="phase5-crash-recovery",
            camera_label="station-recovery",
            camera_id="recovery",
            camera_identity_strategy="index_fallback",
            interval_minutes=1,
            duration_hours=1,
            operator="phase5-driver",
            notes="seeded stale state",
            started_at=started_at,
            planned_stop_at=started_at + timedelta(hours=1),
            images_captured=1,
        )
        atomic_write_json(paths.metadata_path, metadata)
        append_log_line(paths.log_path, started_at, "START", "experiment=phase5-crash-recovery camera=station-recovery interval=1min duration=1h")
        atomic_write_json(
            state_path,
            {
                "running": [
                    {
                        "experiment_id": paths.experiment_id,
                        "camera_label": "station-recovery",
                        "next_capture_at": (started_at + timedelta(minutes=1)).isoformat(timespec="seconds"),
                        "planned_stop_at": (started_at + timedelta(hours=1)).isoformat(timespec="seconds"),
                        "images_captured": 1,
                    }
                ]
            },
        )
        recovered = RunningStateManager(state_path).recover_startup(
            experiments_dir=experiments_dir,
            startup_time=local_now(),
        )
        if paths.experiment_id not in recovered:
            raise ScenarioFailure("stale experiment was not recovered")
        _assert_end_reason(paths.root, "unknown")
        _assert_state_empty(state_path)
        return paths.experiment_id


class _ScheduledFailures:
    def __init__(self, scheduled_results: list[bool | str]) -> None:
        self.scheduled_results = scheduled_results
        self.calls = 0
        self.scheduled_index = 0
        self.remaining_attempts = 0

    def capture(self, camera: CameraInfo) -> Any:
        self.calls += 1
        if self.calls == 1:
            return ONE_PIXEL_JPEG
        if self.scheduled_index >= len(self.scheduled_results):
            return ONE_PIXEL_JPEG
        result = self.scheduled_results[self.scheduled_index]
        if result is False:
            self.scheduled_index += 1
            return ONE_PIXEL_JPEG
        if self.remaining_attempts <= 0:
            self.remaining_attempts = 3
        self.remaining_attempts -= 1
        if self.remaining_attempts == 0:
            self.scheduled_index += 1
        if result == "unavailable":
            raise RuntimeError(f"Configured camera {camera.label!r} was not detected")
        raise RuntimeError("induced camera read failure")


class _ScheduledSaveFailure:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    def save(self, image: Any, output_path: Path, *, quality: int | None = None) -> Path:
        self.calls += 1
        if self.calls > 1:
            raise self.exc
        return _save_jpeg(image, output_path, quality=quality)


class _TempConfig:
    def __init__(self, root: Path, labels: tuple[str, ...]) -> None:
        self.root = root
        self.cameras_path = root / "cameras.json"
        self.state_path = root / "running_state.json"
        cameras = []
        for index, label in enumerate(labels):
            cameras.append(
                {
                    "label": label,
                    "identity_strategy": "hardware_id",
                    "stable_id": f"hardware-{label}",
                    "last_seen_index": index,
                    "warnings": [],
                }
            )
        self.cameras_path.write_text(json.dumps({"cameras": cameras}, indent=2) + "\n", encoding="utf-8")

    def __enter__(self) -> "_TempConfig":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def _temp_config(*labels: str) -> _TempConfig:
    root = Path(tempfile.mkdtemp(prefix="labcam-phase5-config-")).resolve()
    return _TempConfig(root, labels)


def _engine(
    experiments_dir: Path,
    config: _TempConfig,
    *,
    capture_func: Callable[[CameraInfo], Any] | None = None,
    camera_check_func: Callable[[CameraInfo], None] | None = None,
    save_jpeg_func: Callable[..., Path] | None = None,
    disk_usage_func: Callable[[Path], shutil._ntuple_diskusage] = shutil.disk_usage,
) -> CaptureEngine:
    return CaptureEngine(
        experiments_dir=experiments_dir,
        cameras_path=config.cameras_path,
        state_path=config.state_path,
        capture_func=capture_func or _capture_ok,
        camera_check_func=camera_check_func or _camera_check_ok,
        save_jpeg_func=save_jpeg_func or _save_jpeg,
        disk_usage_func=disk_usage_func,
        poll_floor_seconds=0.05,
    )


def _start(engine: CaptureEngine, camera_label: str, name: str) -> str:
    return engine.start_experiment(
        ExperimentConfig(
            name=name,
            camera_label=camera_label,
            interval_minutes=0.01,
            duration_hours=0.25,
            operator="phase5-driver",
        )
    )


def _capture_ok(_: CameraInfo) -> bytes:
    return ONE_PIXEL_JPEG


def _camera_check_ok(_: CameraInfo) -> None:
    return None


def _save_jpeg(image: Any, output_path: Path, *, quality: int | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image if isinstance(image, bytes) else ONE_PIXEL_JPEG)
    return output_path.resolve()


def _experiment(engine: CaptureEngine, experiment_id: str) -> dict[str, Any]:
    for experiment in engine.list_experiments():
        if experiment.get("experiment_id") == experiment_id:
            return experiment
    raise ScenarioFailure(f"experiment not found: {experiment_id}")


def _finished(engine: CaptureEngine, experiment_id: str) -> dict[str, Any]:
    experiment = _experiment(engine, experiment_id)
    if experiment.get("status") == "capturing":
        return {}
    return experiment


def _station(engine: CaptureEngine, camera_label: str) -> dict[str, Any]:
    for station in _station_status(engine):
        if station.get("camera_label") == camera_label:
            return station
    raise ScenarioFailure(f"station not found: {camera_label}")


def _wait_for(predicate: Callable[[], bool], *, timeout: float = 6) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise ScenarioFailure("timed out waiting for scenario condition")


def _assert_not_terminal_storage(experiment: dict[str, Any]) -> None:
    if experiment.get("end_reason") in {"disk_full", "storage_failed"}:
        raise ScenarioFailure(f"camera failure was misclassified as {experiment['end_reason']}")


def _assert_end_reason(folder: Path, reason: str) -> None:
    metadata = read_json_file(folder / "metadata.json")
    if metadata.get("end_reason") != reason:
        raise ScenarioFailure(f"{folder} end_reason={metadata.get('end_reason')}, expected {reason}")
    if reason != "unknown":
        log_text = (folder / "capture_log.txt").read_text(encoding="utf-8")
        if f"reason={reason}" not in log_text:
            raise ScenarioFailure(f"{folder} log missing STOP reason={reason}")


def _assert_state_empty(state_path: Path) -> None:
    state = read_json_file(state_path)
    if state.get("running") != []:
        raise ScenarioFailure(f"{state_path} is not empty")


def _state_is_empty(state_path: Path) -> bool:
    try:
        return read_json_file(state_path).get("running") == []
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
