#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labcam.cameras.interface import CameraInfo
from labcam.engine import CaptureEngine, ExperimentConfig
from labcam.engine.storage import (
    build_metadata,
    create_experiment_paths,
    local_now,
    read_json_file,
    write_metadata,
)
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


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="labcam-phase6-task6-")).resolve()
    scenarios: list[tuple[str, Callable[[Path], str]]] = [
        ("add note", scenario_add_note),
        ("edit note", scenario_edit_note),
        ("blank save deletes note", scenario_blank_save_deletes),
        ("metadata notes unchanged", scenario_metadata_unchanged),
        ("active run blocked", scenario_active_run_blocked),
        ("status card note link", scenario_status_card_note_link),
        ("invalid ids rejected", scenario_invalid_ids_rejected),
    ]

    print(f"Phase 6 Task 6 driver root={root}")
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


def scenario_add_note(root: Path) -> str:
    config = _temp_config(root, "add")
    experiment_id = _finalized_experiment(config, "add-note", start_notes="before run")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.post(
            f"/api/experiments/{experiment_id}/post-notes",
            json={"notes": "Observed clean separation after 30 minutes.\n"},
        )
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Save failed: {response.status_code} {payload}")
        note_path = config.experiments_dir / experiment_id / "post_notes.txt"
        if note_path.read_text(encoding="utf-8") != "Observed clean separation after 30 minutes.\n":
            raise ScenarioFailure("post_notes.txt did not contain the saved note")
        if not payload["has_post_notes"]:
            raise ScenarioFailure(f"payload did not report note presence: {payload}")
        return "post_notes.txt created with plain text"
    finally:
        engine.shutdown_cleanly()


def scenario_edit_note(root: Path) -> str:
    config = _temp_config(root, "edit")
    experiment_id = _finalized_experiment(config, "edit-note", start_notes="")
    note_path = config.experiments_dir / experiment_id / "post_notes.txt"
    note_path.write_text("first note\n", encoding="utf-8")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.post(
            f"/api/experiments/{experiment_id}/post-notes",
            json={"notes": "revised note\nwith second line"},
        )
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Edit failed: {response.status_code} {payload}")
        if note_path.read_text(encoding="utf-8") != "revised note\nwith second line":
            raise ScenarioFailure("post_notes.txt was not replaced")
        get_response = client.get(f"/api/experiments/{experiment_id}/post-notes")
        get_payload = get_response.get_json()
        if get_payload["post_notes"] != "revised note\nwith second line":
            raise ScenarioFailure(f"GET returned stale notes: {get_payload}")
        return "existing post-run note replaced safely"
    finally:
        engine.shutdown_cleanly()


def scenario_blank_save_deletes(root: Path) -> str:
    config = _temp_config(root, "blank")
    experiment_id = _finalized_experiment(config, "blank-note", start_notes="")
    note_path = config.experiments_dir / experiment_id / "post_notes.txt"
    note_path.write_text("remove me", encoding="utf-8")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.post(
            f"/api/experiments/{experiment_id}/post-notes",
            json={"notes": "   \n\t  "},
        )
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Blank save failed: {response.status_code} {payload}")
        if note_path.exists():
            raise ScenarioFailure("blank save did not delete post_notes.txt")
        if payload["has_post_notes"] or payload["post_notes"]:
            raise ScenarioFailure(f"blank save payload still reports notes: {payload}")
        return "blank save removes post_notes.txt"
    finally:
        engine.shutdown_cleanly()


def scenario_metadata_unchanged(root: Path) -> str:
    config = _temp_config(root, "metadata")
    experiment_id = _finalized_experiment(config, "metadata-note", start_notes="start-time note")
    metadata_path = config.experiments_dir / experiment_id / "metadata.json"
    before = metadata_path.read_text(encoding="utf-8")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.post(
            f"/api/experiments/{experiment_id}/post-notes",
            json={"notes": "post-run note"},
        )
        if response.status_code != 200:
            raise ScenarioFailure(f"Save failed: {response.status_code} {response.get_json()}")
        after = metadata_path.read_text(encoding="utf-8")
        if before != after:
            raise ScenarioFailure("metadata.json changed during post-note save")
        metadata = read_json_file(metadata_path)
        if metadata["notes"] != "start-time note":
            raise ScenarioFailure(f"metadata notes changed: {metadata}")
        return "metadata.json start notes preserved"
    finally:
        engine.shutdown_cleanly()


def scenario_active_run_blocked(root: Path) -> str:
    config = _temp_config(root, "active")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    experiment_id: str | None = None
    try:
        _confirm_all(engine)
        experiment_id = engine.start_experiment(_experiment_config("active-note"))
        get_response = client.get(f"/api/experiments/{experiment_id}/post-notes")
        post_response = client.post(
            f"/api/experiments/{experiment_id}/post-notes",
            json={"notes": "too early"},
        )
        if get_response.status_code != 409 or post_response.status_code != 409:
            raise ScenarioFailure(
                f"active notes were not blocked: GET {get_response.status_code}, POST {post_response.status_code}"
            )
        status = client.get("/api/status").get_json()
        station = status["stations"][0]
        if station.get("post_notes_url") is not None or station.get("has_post_notes"):
            raise ScenarioFailure(f"active station exposed editable notes: {station}")
        return "active experiment notes API and status controls blocked"
    finally:
        if experiment_id:
            engine.stop_experiment(experiment_id)
        engine.shutdown_cleanly()


def scenario_status_card_note_link(root: Path) -> str:
    config = _temp_config(root, "status")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    experiment_id: str | None = None
    try:
        _confirm_all(engine)
        experiment_id = engine.start_experiment(_experiment_config("status-note"))
        engine.stop_experiment(experiment_id)
        _wait_for(lambda: _experiment_status(engine, experiment_id) != "capturing")
        status = client.get("/api/status").get_json()
        station = status["stations"][0]
        if station.get("post_notes_url") != f"/experiments/{experiment_id}/notes":
            raise ScenarioFailure(f"terminal station missing notes URL: {station}")
        if station.get("has_post_notes"):
            raise ScenarioFailure(f"newly stopped station unexpectedly has notes: {station}")
        save = client.post(
            f"/api/experiments/{experiment_id}/post-notes",
            json={"notes": "status-visible note"},
        )
        if save.status_code != 200:
            raise ScenarioFailure(f"status note save failed: {save.status_code} {save.get_json()}")
        status_after = client.get("/api/status").get_json()
        station_after = status_after["stations"][0]
        if not station_after.get("has_post_notes"):
            raise ScenarioFailure(f"station did not report saved note: {station_after}")
        page = client.get(f"/experiments/{experiment_id}/notes")
        if page.status_code != 200 or b"post-notes-root" not in page.data:
            raise ScenarioFailure(f"notes page failed: {page.status_code}")
        return "terminal status card exposes add/edit notes link"
    finally:
        if experiment_id and _experiment_status(engine, experiment_id) == "capturing":
            engine.stop_experiment(experiment_id)
        engine.shutdown_cleanly()


def scenario_invalid_ids_rejected(root: Path) -> str:
    config = _temp_config(root, "invalid")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        bad = client.get("/api/experiments/bad$id/post-notes")
        traversal = client.get("/api/experiments/..%5Csecret/post-notes")
        missing = client.get("/api/experiments/2026-05-31-missing-station1/post-notes")
        if bad.status_code != 400:
            raise ScenarioFailure(f"bad id was not rejected as invalid: {bad.status_code}")
        if traversal.status_code != 400:
            raise ScenarioFailure(f"traversal id was not rejected as invalid: {traversal.status_code}")
        if missing.status_code != 404:
            raise ScenarioFailure(f"missing experiment did not return not found: {missing.status_code}")
        return "invalid, traversal, and missing experiment ids rejected"
    finally:
        engine.shutdown_cleanly()


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
                "default_interval_minutes": 0.01,
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
                    }
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


def _engine(config: TempConfig) -> CaptureEngine:
    return CaptureEngine(
        settings_path=config.settings_path,
        cameras_path=config.cameras_path,
        state_path=config.state_path,
        capture_func=_capture_ok,
        preview_func=_capture_ok,
        camera_check_func=lambda _: None,
        save_jpeg_func=_save_jpeg,
        poll_floor_seconds=0.01,
        recover_stale=True,
    )


def _finalized_experiment(config: TempConfig, name: str, *, start_notes: str) -> str:
    started_at = local_now() - timedelta(minutes=10)
    ended_at = local_now() - timedelta(minutes=2)
    planned_stop_at = started_at + timedelta(minutes=8)
    paths = create_experiment_paths(
        experiments_dir=config.experiments_dir,
        experiment_name=name,
        camera_label="station1",
        started_at=started_at,
    )
    metadata = build_metadata(
        name=name,
        camera_label="station1",
        camera_id="mock-1",
        camera_identity_strategy="hardware_id",
        interval_minutes=1,
        duration_hours=0.2,
        operator="tester",
        notes=start_notes,
        started_at=started_at,
        planned_stop_at=planned_stop_at,
        ended_at=ended_at,
        end_reason="completed",
        images_captured=1,
    )
    write_metadata(paths, metadata)
    paths.log_path.write_text("capture log\n", encoding="utf-8")
    paths.images_dir.joinpath("0000_2026-05-31T10-00-00.jpg").write_bytes(ONE_PIXEL_JPEG)
    return paths.experiment_id


def _experiment_config(name: str) -> ExperimentConfig:
    return ExperimentConfig(
        name=name,
        camera_label="station1",
        interval_minutes=0.01,
        duration_hours=0.01,
        operator="tester",
        notes="start note",
    )


def _confirm_all(engine: CaptureEngine) -> None:
    for camera in engine.list_cameras():
        engine.confirm_camera(camera.label)


def _capture_ok(_: CameraInfo) -> object:
    return object()


def _save_jpeg(_: object, path: Path, *, quality: int = 90) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ONE_PIXEL_JPEG)
    return path


def _experiment_status(engine: CaptureEngine, experiment_id: str) -> str | None:
    for experiment in engine.list_experiments():
        if experiment.get("experiment_id") == experiment_id:
            return str(experiment.get("status"))
    return None


def _wait_for(predicate: Callable[[], bool], *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise ScenarioFailure("timed out waiting for condition")


if __name__ == "__main__":
    raise SystemExit(main())
