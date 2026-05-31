#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labcam.cameras.interface import CameraInfo
from labcam.engine import CaptureEngine
from labcam.engine.storage import (
    build_metadata,
    create_experiment_paths,
    local_now,
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
    root = Path(tempfile.mkdtemp(prefix="labcam-phase6-task7-")).resolve()
    scenarios: list[tuple[str, Callable[[Path], str]]] = [
        ("list experiments", scenario_list_experiments),
        ("filter by station and date", scenario_filters),
        ("detail and latest still", scenario_detail_and_latest),
        ("malformed folders", scenario_malformed_folders),
        ("large image count", scenario_large_image_count),
        ("invalid ids rejected", scenario_invalid_ids_rejected),
    ]

    print(f"Phase 6 Task 7 driver root={root}")
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


def scenario_list_experiments(root: Path) -> str:
    config = _temp_config(root, "list")
    first = _finalized_experiment(config, "trial-a", camera_label="station1", images=2)
    second = _finalized_experiment(config, "trial-b", camera_label="station2", images=1)
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.get("/api/experiments")
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"list failed: {response.status_code} {payload}")
        ids = {item["experiment_id"] for item in payload["experiments"]}
        if {first, second} - ids:
            raise ScenarioFailure(f"expected experiments missing: {payload}")
        page = client.get("/experiments")
        if page.status_code != 200 or b"experiment-list" not in page.data:
            raise ScenarioFailure(f"experiments page did not render: {page.status_code}")
        return "completed folders listed with browser page"
    finally:
        engine.shutdown_cleanly()


def scenario_filters(root: Path) -> str:
    config = _temp_config(root, "filters")
    day_one = local_now() - timedelta(days=1)
    day_two = local_now()
    _finalized_experiment(config, "older", camera_label="station1", started_at=day_one)
    target = _finalized_experiment(config, "today", camera_label="station2", started_at=day_two)
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        date_value = day_two.date().isoformat()
        response = client.get(f"/api/experiments?date={date_value}&station=station2")
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"filter failed: {response.status_code} {payload}")
        experiments = payload["experiments"]
        if len(experiments) != 1 or experiments[0]["experiment_id"] != target:
            raise ScenarioFailure(f"filters did not isolate target: {payload}")
        if "station1" not in payload["stations"] or date_value not in payload["dates"]:
            raise ScenarioFailure(f"filter options missing from unfiltered set: {payload}")
        return "date and station filters narrowed the archive"
    finally:
        engine.shutdown_cleanly()


def scenario_detail_and_latest(root: Path) -> str:
    config = _temp_config(root, "detail")
    experiment_id = _finalized_experiment(
        config,
        "detail-run",
        camera_label="station1",
        images=3,
        post_notes="post-run observation",
        start_notes="start note",
    )
    before = _snapshot_experiment_files(config.experiments_dir / experiment_id)
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.get(f"/api/experiments/{experiment_id}")
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"detail failed: {response.status_code} {payload}")
        experiment = payload["experiment"]
        if experiment["capture_log"]["line_count"] < 3 or experiment["capture_log"]["error_count"] != 1:
            raise ScenarioFailure(f"log summary incorrect: {experiment['capture_log']}")
        if experiment["post_notes"] != "post-run observation":
            raise ScenarioFailure(f"post-run notes missing: {experiment}")
        if not experiment["latest_image_url"] or experiment["latest_image"] != "0002_2026-05-31T10-02-00.jpg":
            raise ScenarioFailure(f"latest image not reported: {experiment}")
        latest = client.get(experiment["latest_image_url"])
        if latest.status_code != 200 or latest.mimetype != "image/jpeg":
            raise ScenarioFailure(f"latest route failed: {latest.status_code} {latest.mimetype}")
        page = client.get(f"/experiments/{experiment_id}")
        if page.status_code != 200 or b"experiment-detail-root" not in page.data:
            raise ScenarioFailure(f"detail page did not render: {page.status_code}")
        after = _snapshot_experiment_files(config.experiments_dir / experiment_id)
        if before != after:
            raise ScenarioFailure("browser/detail/latest routes mutated experiment files")
        return "detail payload, notes, log summary, and latest still are read-only"
    finally:
        engine.shutdown_cleanly()


def scenario_malformed_folders(root: Path) -> str:
    config = _temp_config(root, "malformed")
    missing = config.experiments_dir / "2026-05-31_missing-metadata_station1"
    missing.joinpath("images").mkdir(parents=True)
    malformed = config.experiments_dir / "2026-05-31_bad-metadata_station2"
    malformed.mkdir(parents=True)
    malformed.joinpath("metadata.json").write_text("{not json", encoding="utf-8")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.get("/api/experiments")
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"malformed list failed: {response.status_code} {payload}")
        by_id = {item["experiment_id"]: item for item in payload["experiments"]}
        if by_id[missing.name]["metadata_status"] != "missing":
            raise ScenarioFailure(f"missing metadata not reported: {by_id[missing.name]}")
        if by_id[malformed.name]["metadata_status"] != "malformed":
            raise ScenarioFailure(f"malformed metadata not reported: {by_id[malformed.name]}")
        detail = client.get(f"/api/experiments/{malformed.name}").get_json()["experiment"]
        if detail["status"] != "incomplete" or not detail["warnings"]:
            raise ScenarioFailure(f"malformed detail warning missing: {detail}")
        return "missing and malformed metadata surfaced as incomplete"
    finally:
        engine.shutdown_cleanly()


def scenario_large_image_count(root: Path) -> str:
    config = _temp_config(root, "large")
    experiment_id = _finalized_experiment(config, "many-images", camera_label="station1", images=150)
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.get(f"/api/experiments/{experiment_id}")
        payload = response.get_json()
        experiment = payload["experiment"]
        if response.status_code != 200:
            raise ScenarioFailure(f"large detail failed: {response.status_code} {payload}")
        if experiment["images_captured"] != 150:
            raise ScenarioFailure(f"large image count incorrect: {experiment['images_captured']}")
        if experiment["latest_image"] != "0149_2026-05-31T10-149-00.jpg":
            raise ScenarioFailure(f"large latest image incorrect: {experiment['latest_image']}")
        if "images" in experiment:
            raise ScenarioFailure("detail payload exposed a full image list")
        return "large run reports count and latest still only"
    finally:
        engine.shutdown_cleanly()


def scenario_invalid_ids_rejected(root: Path) -> str:
    config = _temp_config(root, "invalid")
    engine = _engine(config)
    app = create_app(engine)
    client = app.test_client()
    try:
        bad_detail = client.get("/api/experiments/bad$id")
        traversal_detail = client.get("/api/experiments/..%5Csecret")
        traversal_latest = client.get("/api/experiments/..%5Csecret/latest")
        missing_latest = client.get("/api/experiments/2026-05-31_missing_station1/latest")
        if bad_detail.status_code != 400:
            raise ScenarioFailure(f"bad detail id not rejected: {bad_detail.status_code}")
        if traversal_detail.status_code != 400 or traversal_latest.status_code != 400:
            raise ScenarioFailure(
                f"traversal ids not rejected: detail={traversal_detail.status_code} latest={traversal_latest.status_code}"
            )
        if missing_latest.status_code != 404:
            raise ScenarioFailure(f"missing latest did not return 404: {missing_latest.status_code}")
        return "invalid and traversal ids rejected"
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


def _finalized_experiment(
    config: TempConfig,
    name: str,
    *,
    camera_label: str,
    images: int = 1,
    post_notes: str = "",
    start_notes: str = "",
    started_at: Any = None,
) -> str:
    started_at = started_at or local_now() - timedelta(minutes=10)
    ended_at = started_at + timedelta(minutes=8)
    planned_stop_at = started_at + timedelta(minutes=8)
    paths = create_experiment_paths(
        experiments_dir=config.experiments_dir,
        experiment_name=name,
        camera_label=camera_label,
        started_at=started_at,
    )
    metadata = build_metadata(
        name=name,
        camera_label=camera_label,
        camera_id=f"mock-{camera_label}",
        camera_identity_strategy="hardware_id",
        interval_minutes=1,
        duration_hours=0.2,
        operator="tester",
        notes=start_notes,
        started_at=started_at,
        planned_stop_at=planned_stop_at,
        ended_at=ended_at,
        end_reason="completed",
        images_captured=images,
    )
    write_metadata(paths, metadata)
    paths.log_path.write_text(
        "\n".join(
            [
                "2026-05-31T10:00:00+03:00  START   experiment=test",
                "2026-05-31T10:01:00+03:00  ERROR   seq=0001 retry 1",
                "2026-05-31T10:02:00+03:00  STOP    reason=completed images=1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    for index in range(images):
        paths.images_dir.joinpath(f"{index:04d}_2026-05-31T10-{index:02d}-00.jpg").write_bytes(ONE_PIXEL_JPEG)
    if post_notes:
        paths.root.joinpath("post_notes.txt").write_text(post_notes, encoding="utf-8")
    return paths.experiment_id


def _snapshot_experiment_files(folder: Path) -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for path in sorted(item for item in folder.rglob("*") if item.is_file()):
        stat = path.stat()
        snapshot[str(path.relative_to(folder))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


def _capture_ok(_: CameraInfo) -> object:
    return object()


def _save_jpeg(_: object, path: Path, *, quality: int = 90) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(ONE_PIXEL_JPEG)
    return path


if __name__ == "__main__":
    raise SystemExit(main())
