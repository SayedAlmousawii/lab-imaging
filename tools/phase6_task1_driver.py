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
from labcam.engine import CaptureEngine
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
    root = Path(tempfile.mkdtemp(prefix="labcam-phase6-task1-")).resolve()
    scenarios: list[tuple[str, Callable[[Path], str]]] = [
        ("startup gate", scenario_startup_gate),
        ("strong identity confirmation", scenario_strong_identity_confirmation),
        ("index fallback warning", scenario_index_fallback_warning),
        ("unavailable cannot confirm", scenario_unavailable_cannot_confirm),
        ("restart still requires session confirmation", scenario_restart_requires_session_confirmation),
    ]

    print(f"Phase 6 Task 1 driver root={root}")
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


def scenario_startup_gate(root: Path) -> str:
    config = _temp_config(root, "gate", [{"label": "Station A"}])
    engine = _engine(root, config)
    app = create_app(engine)
    client = app.test_client()

    try:
        status_page = client.get("/")
        new_page = client.get("/new")
        verify_page = client.get("/verify-cameras")
        api_status = client.get("/api/status")
        start_response = client.post(
            "/api/experiments",
            json={
                "camera_label": "Station A",
                "name": "phase6-gated",
                "interval_minutes": 5,
                "duration_hours": 1,
                "operator": "driver",
            },
        )
        if status_page.status_code != 302 or "/verify-cameras" not in status_page.location:
            raise ScenarioFailure(f"status page was not gated: {status_page.status_code} {status_page.location}")
        if new_page.status_code != 302 or "/verify-cameras" not in new_page.location:
            raise ScenarioFailure(f"new page was not gated: {new_page.status_code} {new_page.location}")
        if verify_page.status_code != 200 or b"verify.js" not in verify_page.data:
            raise ScenarioFailure(f"verification page did not render: {verify_page.status_code}")
        if api_status.status_code != 200:
            raise ScenarioFailure(f"api status was not readable: {api_status.status_code}")
        if start_response.status_code != 400:
            raise ScenarioFailure(f"experiment start was not blocked: {start_response.status_code}")
        return "dashboard and start API blocked until verification"
    finally:
        engine.shutdown_cleanly()


def scenario_strong_identity_confirmation(root: Path) -> str:
    config = _temp_config(root, "strong", [{"label": "Station A"}])
    engine = _engine(root, config)
    app = create_app(engine)
    client = app.test_client()

    try:
        preview = client.post("/api/preview", json={"camera_label": "Station A"})
        if preview.status_code != 200 or preview.mimetype != "image/jpeg":
            raise ScenarioFailure(f"preview failed: {preview.status_code}")

        confirm = client.post("/api/verification/confirm", json={"camera_label": "Station A"})
        payload = confirm.get_json()
        if confirm.status_code != 200 or payload["required"]:
            raise ScenarioFailure(f"confirm failed: {confirm.status_code} {payload}")

        persisted = json.loads(config.cameras_path.read_text(encoding="utf-8"))
        record = persisted["cameras"][0]
        if not record.get("last_confirmed_at") or record.get("last_confirmed_index") != 0:
            raise ScenarioFailure(f"confirmation metadata missing: {record}")

        status_page = client.get("/")
        if status_page.status_code != 200:
            raise ScenarioFailure(f"status page still gated: {status_page.status_code}")
        return record["last_confirmed_at"]
    finally:
        engine.shutdown_cleanly()


def scenario_index_fallback_warning(root: Path) -> str:
    config = _temp_config(
        root,
        "fallback",
        [
            {
                "label": "Station F",
                "identity_strategy": "index_fallback",
                "stable_id": "index-2",
                "last_seen_index": 2,
                "warnings": ["No stable hardware identity was available."],
            }
        ],
    )
    engine = _engine(root, config)
    app = create_app(engine)
    client = app.test_client()

    try:
        response = client.get("/api/verification")
        payload = response.get_json()
        camera = payload["cameras"][0]
        if not camera["identity_warning"] or camera["identity_strategy"] != "index_fallback":
            raise ScenarioFailure(f"fallback warning missing: {camera}")
        return "weak identity is marked in verification status"
    finally:
        engine.shutdown_cleanly()


def scenario_unavailable_cannot_confirm(root: Path) -> str:
    config = _temp_config(root, "unavailable", [{"label": "Station U"}])

    def preview_unavailable(_: CameraInfo) -> bytes:
        raise RuntimeError("Could not open camera index 8")

    engine = _engine(root, config, preview_func=preview_unavailable)
    app = create_app(engine)
    client = app.test_client()

    try:
        confirm = client.post("/api/verification/confirm", json={"camera_label": "Station U"})
        payload = confirm.get_json()
        if confirm.status_code != 500 or payload["error"]["code"] != "preview_failed":
            raise ScenarioFailure(f"unavailable camera confirmed unexpectedly: {confirm.status_code} {payload}")
        status = client.get("/api/verification").get_json()
        if status["cameras"][0]["confirmed"]:
            raise ScenarioFailure(f"camera marked confirmed after failed preview: {status}")
        return "failed preview kept station unconfirmed"
    finally:
        engine.shutdown_cleanly()


def scenario_restart_requires_session_confirmation(root: Path) -> str:
    config = _temp_config(root, "restart", [{"label": "Station R"}])
    first_engine = _engine(root, config)
    first_app = create_app(first_engine)
    first_client = first_app.test_client()
    try:
        confirm = first_client.post("/api/verification/confirm", json={"camera_label": "Station R"})
        if confirm.status_code != 200:
            raise ScenarioFailure(f"initial confirm failed: {confirm.status_code}")
    finally:
        first_engine.shutdown_cleanly()

    second_engine = _engine(root, config)
    second_app = create_app(second_engine)
    second_client = second_app.test_client()
    try:
        payload = second_client.get("/api/verification").get_json()
        if not payload["required"] or payload["cameras"][0]["confirmed"]:
            raise ScenarioFailure(f"restart reused session confirmation: {payload}")
        if not payload["cameras"][0]["last_confirmed_at"]:
            raise ScenarioFailure(f"persisted confirmation metadata lost: {payload}")
        return "metadata persisted, process gate reset"
    finally:
        second_engine.shutdown_cleanly()


class _TempConfig:
    def __init__(self, root: Path, name: str, records: list[dict[str, Any]]) -> None:
        self.root = (root / name).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cameras_path = self.root / "cameras.json"
        self.state_path = self.root / "running_state.json"
        cameras = []
        for index, record in enumerate(records):
            cameras.append(
                {
                    "label": record["label"],
                    "identity_strategy": record.get("identity_strategy", "hardware_id"),
                    "stable_id": record.get("stable_id", f"hardware-{record['label']}"),
                    "last_seen_index": record.get("last_seen_index", index),
                    "warnings": record.get("warnings", []),
                    **{key: value for key, value in record.items() if key.startswith("last_confirmed_")},
                }
            )
        self.cameras_path.write_text(json.dumps({"cameras": cameras}, indent=2) + "\n", encoding="utf-8")


def _temp_config(root: Path, name: str, records: list[dict[str, Any]]) -> _TempConfig:
    return _TempConfig(root, name, records)


def _engine(
    root: Path,
    config: _TempConfig,
    *,
    preview_func: Callable[[CameraInfo], Any] | None = None,
) -> CaptureEngine:
    return CaptureEngine(
        experiments_dir=root / "experiments",
        cameras_path=config.cameras_path,
        state_path=config.state_path,
        capture_func=_capture_ok,
        preview_func=preview_func or _capture_ok,
        camera_check_func=_camera_check_ok,
        save_jpeg_func=_save_jpeg,
        disk_usage_func=_disk_usage,
        poll_floor_seconds=0.05,
    )


def _capture_ok(_: CameraInfo) -> bytes:
    return ONE_PIXEL_JPEG


def _camera_check_ok(_: CameraInfo) -> None:
    return None


def _save_jpeg(image: Any, output_path: Path, *, quality: int | None = None) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(image if isinstance(image, bytes) else ONE_PIXEL_JPEG)
    return output_path.resolve()


def _disk_usage(_: Path) -> shutil._ntuple_diskusage:
    return shutil._ntuple_diskusage(total=30_000_000_000, used=1_000_000_000, free=29_000_000_000)


if __name__ == "__main__":
    raise SystemExit(main())
