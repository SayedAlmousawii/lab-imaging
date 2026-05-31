#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labcam.cameras.interface import CameraInfo
from labcam.engine import CaptureEngine, ExperimentConfig
from labcam.engine.storage import read_json_file
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


@dataclass(frozen=True)
class TempConfig:
    root: Path
    experiments_dir: Path
    settings_path: Path
    cameras_path: Path
    state_path: Path


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 5, 31, 10, 0, 0, tzinfo=timezone.utc).astimezone()

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class CaptureRecorder:
    def __init__(self) -> None:
        self.by_label: dict[str, int] = {}

    def __call__(self, camera: CameraInfo) -> object:
        self.by_label[camera.label] = self.by_label.get(camera.label, 0) + 1
        return object()


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="labcam-phase6-task8-")).resolve()
    scenarios: list[tuple[str, Callable[[Path], str]]] = [
        ("enter maintenance pauses captures", scenario_enter_pauses_captures),
        ("resume keeps sequence monotonic", scenario_resume_sequence),
        ("log and metadata evidence", scenario_log_and_metadata),
        ("other station continues", scenario_other_station_continues),
        ("stop during maintenance", scenario_stop_during_maintenance),
        ("invalid transitions", scenario_invalid_transitions),
        ("maintenance preview succeeds", scenario_maintenance_preview_succeeds),
        ("maintenance preview failure", scenario_maintenance_preview_failure),
        ("preview button maintenance only", scenario_preview_button_maintenance_only),
    ]

    print(f"Phase 6 Task 8 driver root={root}")
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


def scenario_enter_pauses_captures(root: Path) -> str:
    config, clock, recorder, engine, client = _runtime(root, "pause")
    try:
        experiment_id = _start(engine, "pause-run")
        response = client.post(
            f"/api/experiments/{experiment_id}/maintenance/start",
            json={"note": "adjusting sample height"},
        )
        payload = response.get_json()
        if response.status_code != 200 or payload["status"] != "maintenance":
            raise ScenarioFailure(f"maintenance start failed: {response.status_code} {payload}")

        clock.advance(0.30)
        time.sleep(0.08)
        images = _image_names(config, experiment_id)
        status = _experiment(engine, experiment_id)
        state = read_json_file(config.state_path)["running"][0]
        if len(images) != 1 or not images[0].startswith("0000_"):
            raise ScenarioFailure(f"captures occurred during maintenance: {images}")
        if recorder.by_label.get("station1") != 1:
            raise ScenarioFailure(f"camera was called during maintenance: {recorder.by_label}")
        if status["maintenance_skipped_capture_count"] < 4:
            raise ScenarioFailure(f"skipped captures were not counted: {status}")
        if state.get("status") != "maintenance" or state.get("maintenance_note") != "adjusting sample height":
            raise ScenarioFailure(f"running_state did not record maintenance: {state}")
        return "scheduled captures paused and running_state recorded maintenance"
    finally:
        engine.shutdown_cleanly()


def scenario_resume_sequence(root: Path) -> str:
    config, clock, _, engine, client = _runtime(root, "resume")
    try:
        experiment_id = _start(engine, "resume-run")
        client.post(f"/api/experiments/{experiment_id}/maintenance/start", json={"note": "mixing"})
        clock.advance(0.25)
        response = client.post(f"/api/experiments/{experiment_id}/maintenance/resume")
        payload = response.get_json()
        if response.status_code != 200 or payload["status"] != "capturing":
            raise ScenarioFailure(f"resume failed: {response.status_code} {payload}")
        if payload["maintenance_skipped_capture_count"] != 4:
            raise ScenarioFailure(f"resume skipped count wrong: {payload}")

        clock.advance(0.07)
        _wait_for(lambda: len(_image_names(config, experiment_id)) == 2)
        images = _image_names(config, experiment_id)
        if images[1].split("_", 1)[0] != "0001":
            raise ScenarioFailure(f"maintenance created sequence gaps: {images}")
        return "resume captured next image as sequence 0001 after four skipped slots"
    finally:
        engine.shutdown_cleanly()


def scenario_log_and_metadata(root: Path) -> str:
    config, clock, _, engine, client = _runtime(root, "evidence")
    try:
        experiment_id = _start(engine, "evidence-run")
        client.post(
            f"/api/experiments/{experiment_id}/maintenance/start",
            json={"note": "cleaned lens"},
        )
        clock.advance(0.13)
        client.post(f"/api/experiments/{experiment_id}/maintenance/resume")
        metadata = read_json_file(config.experiments_dir / experiment_id / "metadata.json")
        events = metadata.get("maintenance_events")
        if not isinstance(events, list) or len(events) != 1:
            raise ScenarioFailure(f"metadata missing maintenance event: {metadata}")
        event = events[0]
        if not event.get("started_at") or not event.get("ended_at"):
            raise ScenarioFailure(f"maintenance event is not closed: {event}")
        if event.get("note") != "cleaned lens" or event.get("skipped_capture_count") != 2:
            raise ScenarioFailure(f"maintenance event content wrong: {event}")
        log_text = (config.experiments_dir / experiment_id / "capture_log.txt").read_text(
            encoding="utf-8"
        )
        if "MAINT   start note=\"cleaned lens\"" not in log_text:
            raise ScenarioFailure(f"maintenance start missing from log: {log_text}")
        if "MAINT   end skipped_captures=2 note=\"cleaned lens\"" not in log_text:
            raise ScenarioFailure(f"maintenance end missing from log: {log_text}")
        return "metadata and append-only log contain the maintenance window"
    finally:
        engine.shutdown_cleanly()


def scenario_other_station_continues(root: Path) -> str:
    config, clock, recorder, engine, client = _runtime(root, "other")
    try:
        station1 = _start(engine, "paused-station", camera_label="station1")
        station2 = _start(engine, "running-station", camera_label="station2")
        client.post(f"/api/experiments/{station1}/maintenance/start", json={"note": "station 1"})
        clock.advance(0.14)
        _wait_for(lambda: recorder.by_label.get("station2", 0) >= 2)
        if len(_image_names(config, station1)) != 1:
            raise ScenarioFailure(f"paused station captured images: {_image_names(config, station1)}")
        if len(_image_names(config, station2)) < 2:
            raise ScenarioFailure(f"other station did not continue: {_image_names(config, station2)}")
        status = client.get("/api/status").get_json()["stations"]
        states = {station["camera_label"]: station["state"] for station in status}
        if states.get("station1") != "maintenance" or states.get("station2") != "running":
            raise ScenarioFailure(f"dashboard states wrong: {states}")
        return "maintenance on one station did not block another station"
    finally:
        engine.shutdown_cleanly()


def scenario_stop_during_maintenance(root: Path) -> str:
    config, clock, _, engine, client = _runtime(root, "stop")
    try:
        experiment_id = _start(engine, "stop-run")
        client.post(f"/api/experiments/{experiment_id}/maintenance/start", json={"note": "manual stop"})
        clock.advance(0.12)
        response = client.post(f"/api/experiments/{experiment_id}/stop")
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"stop failed: {response.status_code} {payload}")
        _wait_for(lambda: _experiment(engine, experiment_id)["status"] == "stopped")
        metadata = read_json_file(config.experiments_dir / experiment_id / "metadata.json")
        event = metadata["maintenance_events"][0]
        if metadata["end_reason"] != "stopped_early":
            raise ScenarioFailure(f"stop reason wrong: {metadata}")
        if not event["ended_at"] or event["skipped_capture_count"] != 2:
            raise ScenarioFailure(f"maintenance was not closed on stop: {event}")
        if read_json_file(config.state_path)["running"]:
            raise ScenarioFailure("running_state still contains stopped experiment")
        return "stop during maintenance finalized cleanly and closed the event"
    finally:
        engine.shutdown_cleanly()


def scenario_invalid_transitions(root: Path) -> str:
    _, _, _, engine, client = _runtime(root, "invalid")
    try:
        experiment_id = _start(engine, "invalid-run")
        missing = client.post("/api/experiments/missing/maintenance/start", json={})
        resume_while_running = client.post(
            f"/api/experiments/{experiment_id}/maintenance/resume"
        )
        first_start = client.post(
            f"/api/experiments/{experiment_id}/maintenance/start",
            json={"note": "once"},
        )
        second_start = client.post(
            f"/api/experiments/{experiment_id}/maintenance/start",
            json={"note": "twice"},
        )
        first_resume = client.post(f"/api/experiments/{experiment_id}/maintenance/resume")
        second_resume = client.post(f"/api/experiments/{experiment_id}/maintenance/resume")
        if missing.status_code != 404:
            raise ScenarioFailure(f"missing experiment was not 404: {missing.status_code}")
        if resume_while_running.status_code != 409:
            raise ScenarioFailure(f"running resume was not 409: {resume_while_running.status_code}")
        if first_start.status_code != 200 or second_start.status_code != 409:
            raise ScenarioFailure(
                f"start transition statuses wrong: {first_start.status_code}, {second_start.status_code}"
            )
        if first_resume.status_code != 200 or second_resume.status_code != 409:
            raise ScenarioFailure(
                f"resume transition statuses wrong: {first_resume.status_code}, {second_resume.status_code}"
            )
        return "invalid maintenance transitions returned 404/409 responses"
    finally:
        engine.shutdown_cleanly()


def scenario_maintenance_preview_succeeds(root: Path) -> str:
    config, _, recorder, engine, client = _runtime(root, "preview")
    try:
        experiment_id = _start(engine, "preview-run")
        client.post(f"/api/experiments/{experiment_id}/maintenance/start", json={"note": "framing"})
        before_images = _image_names(config, experiment_id)
        before_metadata = read_json_file(config.experiments_dir / experiment_id / "metadata.json")
        before_status = _experiment(engine, experiment_id)

        response = client.post("/api/preview", json={"camera_label": "station1"})
        if response.status_code != 200 or response.mimetype != "image/jpeg":
            raise ScenarioFailure(f"maintenance preview failed: {response.status_code} {response.mimetype}")
        if response.data != ONE_PIXEL_JPEG:
            raise ScenarioFailure("maintenance preview did not return the mock JPEG")

        after_images = _image_names(config, experiment_id)
        after_metadata = read_json_file(config.experiments_dir / experiment_id / "metadata.json")
        after_status = _experiment(engine, experiment_id)
        if before_images != after_images:
            raise ScenarioFailure(f"preview wrote experiment images: before={before_images}, after={after_images}")
        if after_metadata.get("images_captured") != before_metadata.get("images_captured"):
            raise ScenarioFailure(f"preview changed metadata image count: {after_metadata}")
        if after_status["maintenance_skipped_capture_count"] != before_status["maintenance_skipped_capture_count"]:
            raise ScenarioFailure(f"preview changed skipped count: {after_status}")
        if recorder.by_label.get("station1") != 2:
            raise ScenarioFailure(f"preview did not use exactly one fresh still capture: {recorder.by_label}")
        return "maintenance preview returned JPEG without changing experiment images or counts"
    finally:
        engine.shutdown_cleanly()


def scenario_maintenance_preview_failure(root: Path) -> str:
    config, _, _, engine, client = _runtime(root, "preview-fail")
    try:
        experiment_id = _start(engine, "preview-fail-run")
        client.post(f"/api/experiments/{experiment_id}/maintenance/start", json={"note": "framing"})
        engine.preview_func = _capture_fail

        response = client.post("/api/preview", json={"camera_label": "station1"})
        payload = response.get_json()
        if response.status_code != 500 or payload["error"]["code"] != "preview_failed":
            raise ScenarioFailure(f"preview failure response wrong: {response.status_code} {payload}")
        status = _experiment(engine, experiment_id)
        if status["status"] != "maintenance":
            raise ScenarioFailure(f"preview failure left maintenance state: {status}")
        if len(_image_names(config, experiment_id)) != 1:
            raise ScenarioFailure(f"preview failure changed experiment images: {_image_names(config, experiment_id)}")
        return "failed maintenance preview returned a clear error and stayed in maintenance"
    finally:
        engine.shutdown_cleanly()


def scenario_preview_button_maintenance_only(root: Path) -> str:
    status_js = (PROJECT_ROOT / "labcam" / "web" / "static" / "status.js").read_text(
        encoding="utf-8"
    )
    running_block = _function_block(status_js, "runningBody", "maintenanceBody")
    maintenance_block = _function_block(status_js, "maintenanceBody", "idleBody")
    if "data-maintenance-preview-id" in running_block:
        raise ScenarioFailure("ordinary running card exposes maintenance preview")
    if "data-maintenance-preview-id" not in maintenance_block:
        raise ScenarioFailure("maintenance card does not expose preview")
    if 'fetch("/api/preview"' not in status_js:
        raise ScenarioFailure("maintenance preview does not reuse /api/preview")
    return "status UI exposes preview only from maintenance cards"


def _runtime(root: Path, name: str) -> tuple[TempConfig, FakeClock, CaptureRecorder, CaptureEngine, Any]:
    config = _temp_config(root, name)
    clock = FakeClock()
    recorder = CaptureRecorder()
    engine = CaptureEngine(
        settings_path=config.settings_path,
        cameras_path=config.cameras_path,
        state_path=config.state_path,
        capture_func=recorder,
        preview_func=recorder,
        camera_check_func=lambda _: None,
        save_jpeg_func=_save_jpeg,
        now_func=clock.now,
        poll_floor_seconds=0.01,
        recover_stale=True,
    )
    _confirm_all(engine)
    recorder.by_label.clear()
    return config, clock, recorder, engine, create_app(engine).test_client()


def _temp_config(root: Path, name: str) -> TempConfig:
    config_root = root / name
    experiments_dir = config_root / "experiments"
    settings_path = config_root / "settings.json"
    cameras_path = config_root / "cameras.json"
    state_path = config_root / "running_state.json"
    config_root.mkdir(parents=True, exist_ok=True)
    experiments_dir.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "experiments_dir": str(experiments_dir),
                "web_port": 5000,
                "allow_lan_access": False,
                "warmup_frames": 0,
                "capture_retries": 0,
                "default_interval_minutes": 0.001,
                "default_duration_hours": 0.01,
                "jpeg_quality": 90,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    cameras_path.write_text(
        json.dumps(
            {
                "cameras": [
                    {
                        "label": "station1",
                        "identity_strategy": "hardware_id",
                        "stable_id": "mock-1",
                        "last_seen_index": 0,
                        "warnings": [],
                    },
                    {
                        "label": "station2",
                        "identity_strategy": "hardware_id",
                        "stable_id": "mock-2",
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
    return TempConfig(
        root=config_root,
        experiments_dir=experiments_dir,
        settings_path=settings_path,
        cameras_path=cameras_path,
        state_path=state_path,
    )


def _start(
    engine: CaptureEngine,
    name: str,
    *,
    camera_label: str = "station1",
) -> str:
    return engine.start_experiment(
        ExperimentConfig(
            name=name,
            camera_label=camera_label,
            interval_minutes=0.001,
            duration_hours=0.01,
            operator="tester",
            notes="start note",
        )
    )


def _confirm_all(engine: CaptureEngine) -> None:
    for camera in engine.list_cameras():
        engine.confirm_camera(camera.label)


def _save_jpeg(_: object, path: Path, *, quality: int = 90) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ONE_PIXEL_JPEG)
    return path


def _capture_fail(_: CameraInfo) -> object:
    raise RuntimeError("camera is not responding")


def _image_names(config: TempConfig, experiment_id: str) -> list[str]:
    return sorted(path.name for path in (config.experiments_dir / experiment_id / "images").glob("*.jpg"))


def _experiment(engine: CaptureEngine, experiment_id: str) -> dict[str, Any]:
    for experiment in engine.list_experiments():
        if experiment.get("experiment_id") == experiment_id:
            return experiment
    raise ScenarioFailure(f"experiment not found: {experiment_id}")


def _wait_for(predicate: Callable[[], bool], *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise ScenarioFailure("timed out waiting for condition")


def _function_block(text: str, start_name: str, next_name: str) -> str:
    start = text.index(f"function {start_name}")
    end = text.index(f"function {next_name}", start)
    return text[start:end]


if __name__ == "__main__":
    raise SystemExit(main())
