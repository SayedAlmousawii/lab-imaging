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

from labcam.cameras import interface as camera_interface
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
    root = Path(tempfile.mkdtemp(prefix="labcam-phase6-task2-")).resolve()
    scenarios: list[tuple[str, Callable[[Path], str]]] = [
        ("fresh process detector", scenario_fresh_process_detector),
        ("detect cameras", scenario_detect_cameras),
        ("assign station", scenario_assign_station),
        ("fallback warning", scenario_fallback_warning),
        ("stress test success", scenario_stress_success),
        ("stress test failure", scenario_stress_failure),
        ("stale preview error", scenario_stale_preview_error),
        ("save resets verification", scenario_save_resets_verification),
        ("detection blocked while running", scenario_detection_blocked_while_running),
    ]

    print(f"Phase 6 Task 2 driver root={root}")
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


def scenario_fresh_process_detector(root: Path) -> str:
    calls: list[list[str]] = []
    original_run = camera_interface.subprocess.run

    class _Result:
        def __init__(self, stdout: str) -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(command: list[str], **kwargs: Any) -> _Result:
        calls.append(command)
        if kwargs.get("cwd") != camera_interface.PROJECT_ROOT:
            raise ScenarioFailure(f"Fresh detector cwd was wrong: {kwargs.get('cwd')}")
        if "--preview-index" in command:
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_bytes(ONE_PIXEL_JPEG)
            return _Result(json.dumps({"preview_path": str(output_path)}))
        return _Result(
            json.dumps(
                {
                    "cameras": [
                        {
                            "label": "Fresh USB",
                            "identity_strategy": "index_fallback",
                            "stable_id": "3",
                            "index": 3,
                            "warnings": ["fresh process result"],
                        }
                    ]
                }
            )
        )

    camera_interface.subprocess.run = fake_run  # type: ignore[assignment]
    try:
        cameras = camera_interface.list_cameras_fresh_process(timeout_seconds=1)
        preview_path = camera_interface.preview_camera_fresh_process(
            3,
            root / "fresh-preview.jpg",
            quality=90,
            timeout_seconds=1,
        )
    finally:
        camera_interface.subprocess.run = original_run  # type: ignore[assignment]

    if not calls or calls[0][-2:] != ["-m", "labcam.cameras.probe"]:
        raise ScenarioFailure(f"Fresh detector did not call probe module: {calls}")
    if len(cameras) != 1 or cameras[0].label != "Fresh USB" or cameras[0].index != 3:
        raise ScenarioFailure(f"Fresh detector parse failed: {cameras}")
    if not preview_path.exists() or "--preview-index" not in calls[1]:
        raise ScenarioFailure(f"Fresh preview process was not used: {calls}")
    return "fresh-process probe and detected preview verified"


def scenario_detect_cameras(root: Path) -> str:
    engine = _engine(root, "detect")
    app = create_app(engine)
    client = app.test_client()
    try:
        page = client.get("/cameras")
        if page.status_code != 200 or b"cameras.js" not in page.data:
            raise ScenarioFailure(f"Cameras page did not render: {page.status_code}")
        gated_status = client.get("/")
        if gated_status.status_code != 302 or "/cameras" not in gated_status.location:
            raise ScenarioFailure(
                f"Missing camera config did not route to setup: {gated_status.status_code} {gated_status.location}"
            )

        response = client.get("/api/cameras/detected")
        payload = response.get_json()
        if response.status_code != 200 or len(payload["detected"]) != 2:
            raise ScenarioFailure(f"Detection response wrong: {response.status_code} {payload}")
        if payload["configured"] != []:
            raise ScenarioFailure(f"Unexpected configured cameras without config: {payload}")
        return "two detected cameras returned without existing config"
    finally:
        engine.shutdown_cleanly()


def scenario_assign_station(root: Path) -> str:
    config = _temp_config(root, "assign", with_initial_config=False)
    engine = _engine(root, "assign", config=config)
    app = create_app(engine)
    client = app.test_client()
    try:
        preview = client.post("/api/cameras/detected/preview", json={"camera_index": 0})
        if preview.status_code != 200 or preview.mimetype != "image/jpeg":
            raise ScenarioFailure(f"Detected preview failed: {preview.status_code}")

        save = client.post(
            "/api/cameras/config",
            json={
                "mappings": [
                    {"camera_index": 0, "label": "station1", "notes": "Left bench"},
                    {"camera_index": 1, "label": "station2", "notes": "Right bench"},
                ]
            },
        )
        payload = save.get_json()
        if save.status_code != 200:
            raise ScenarioFailure(f"Save failed: {save.status_code} {payload}")

        saved = json.loads(config.cameras_path.read_text(encoding="utf-8"))
        records = saved["cameras"]
        if records[0]["label"] != "station1" or records[0]["last_seen_index"] != 0:
            raise ScenarioFailure(f"First saved record incompatible: {records[0]}")
        if records[1]["notes"] != "Right bench":
            raise ScenarioFailure(f"Notes not saved: {records[1]}")
        return "config/cameras.json saved with two station records"
    finally:
        engine.shutdown_cleanly()


def scenario_fallback_warning(root: Path) -> str:
    engine = _engine(root, "fallback")
    app = create_app(engine)
    client = app.test_client()
    try:
        payload = client.get("/api/cameras/detected").get_json()
        fallback = payload["detected"][1]
        if not fallback["identity_warning"] or fallback["identity_strategy"] != "index_fallback":
            raise ScenarioFailure(f"Fallback warning missing: {fallback}")
        if not fallback["warnings"]:
            raise ScenarioFailure(f"Fallback warning text missing: {fallback}")
        return "index_fallback detection is flagged"
    finally:
        engine.shutdown_cleanly()


def scenario_stress_success(root: Path) -> str:
    engine = _engine(root, "stress-ok")
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.post(
            "/api/cameras/stress-test",
            json={"camera_indexes": [0, 1], "cycles": 3},
        )
        payload = response.get_json()
        if response.status_code != 200:
            raise ScenarioFailure(f"Stress success failed: {response.status_code} {payload}")
        counts = [(result["passed"], result["cycles"], result["ok"]) for result in payload["results"]]
        if counts != [(3, 3, True), (3, 3, True)]:
            raise ScenarioFailure(f"Unexpected stress counts: {counts}")
        return "both cameras reported 3/3 passed"
    finally:
        engine.shutdown_cleanly()


def scenario_stress_failure(root: Path) -> str:
    calls: dict[int, int] = {}

    def capture_with_failure(camera: CameraInfo) -> bytes:
        calls[camera.index] = calls.get(camera.index, 0) + 1
        if camera.index == 1 and calls[camera.index] == 2:
            raise RuntimeError("Could not read frame from camera index 1")
        return ONE_PIXEL_JPEG

    engine = _engine(root, "stress-fail", capture_func=capture_with_failure)
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.post(
            "/api/cameras/stress-test",
            json={"camera_indexes": [1], "cycles": 4},
        )
        payload = response.get_json()
        result = payload["results"][0]
        if response.status_code != 200 or result["ok"] or result["passed"] != 1:
            raise ScenarioFailure(f"Stress failure not reported: {response.status_code} {payload}")
        if not result["failures"] or "cycle 2" not in result["failures"][0]:
            raise ScenarioFailure(f"Failure detail missing: {result}")
        return "failure reported without API crash"
    finally:
        engine.shutdown_cleanly()


def scenario_stale_preview_error(root: Path) -> str:
    def preview_no_longer_detected(
        camera_index: int,
        output_path: Path,
        *,
        quality: int | None = None,
    ) -> Path:
        raise RuntimeError(f"Camera index {camera_index} is not detected.")

    config = _temp_config(root, "stale-preview", with_initial_config=False)
    engine = CaptureEngine(
        experiments_dir=root / "stale-preview" / "experiments",
        cameras_path=config.cameras_path,
        state_path=config.state_path,
        capture_func=_capture_ok,
        preview_func=_capture_ok,
        camera_check_func=_camera_check_ok,
        detected_camera_func=_detected_cameras,
        detected_preview_func=preview_no_longer_detected,
        save_jpeg_func=_save_jpeg,
        disk_usage_func=_disk_usage,
        poll_floor_seconds=0.05,
    )
    app = create_app(engine)
    client = app.test_client()
    try:
        response = client.post("/api/cameras/detected/preview", json={"camera_index": 1})
        payload = response.get_json()
        message = payload["error"]["message"]
        if response.status_code != 500 or "Camera list changed" not in message:
            raise ScenarioFailure(f"Stale preview message wrong: {response.status_code} {payload}")
        return "vanished index returns changed-list preview message"
    finally:
        engine.shutdown_cleanly()


def scenario_save_resets_verification(root: Path) -> str:
    config = _temp_config(root, "reset", with_initial_config=True)
    engine = _engine(root, "reset", config=config)
    app = create_app(engine)
    client = app.test_client()
    try:
        confirm = client.post("/api/verification/confirm", json={"camera_label": "station1"})
        if confirm.status_code != 200 or confirm.get_json()["required"]:
            raise ScenarioFailure(f"Initial confirmation failed: {confirm.status_code} {confirm.get_json()}")

        save = client.post(
            "/api/cameras/config",
            json={"mappings": [{"camera_index": 0, "label": "station1", "notes": "Updated"}]},
        )
        payload = save.get_json()
        if save.status_code != 200:
            raise ScenarioFailure(f"Save failed: {save.status_code} {payload}")
        verification = payload["verification"]
        if not verification["required"] or verification["cameras"][0]["confirmed"]:
            raise ScenarioFailure(f"Verification was not reset: {verification}")
        return "saving mapping cleared process confirmation"
    finally:
        engine.shutdown_cleanly()


def scenario_detection_blocked_while_running(root: Path) -> str:
    config = _temp_config(root, "blocked", with_initial_config=True)
    engine = _engine(root, "blocked", config=config)
    app = create_app(engine)
    client = app.test_client()
    try:
        confirm = client.post("/api/verification/confirm", json={"camera_label": "station1"})
        if confirm.status_code != 200:
            raise ScenarioFailure(f"Confirmation failed: {confirm.status_code} {confirm.get_json()}")

        start = client.post(
            "/api/experiments",
            json={
                "camera_label": "station1",
                "name": "blocked-detect",
                "interval_minutes": 5,
                "duration_hours": 1,
                "operator": "driver",
            },
        )
        if start.status_code != 200:
            raise ScenarioFailure(f"Experiment start failed: {start.status_code} {start.get_json()}")

        detect = client.get("/api/cameras/detected")
        payload = detect.get_json()
        if detect.status_code != 409 or payload["error"]["code"] != "camera_setup_busy":
            raise ScenarioFailure(f"Detection was not blocked: {detect.status_code} {payload}")
        return "camera setup detection returned busy while experiment was running"
    finally:
        engine.shutdown_cleanly()


class _TempConfig:
    def __init__(self, root: Path, name: str, *, with_initial_config: bool) -> None:
        self.root = (root / name).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.cameras_path = self.root / "cameras.json"
        self.state_path = self.root / "running_state.json"
        if with_initial_config:
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


def _temp_config(root: Path, name: str, *, with_initial_config: bool) -> _TempConfig:
    return _TempConfig(root, name, with_initial_config=with_initial_config)


def _engine(
    root: Path,
    name: str,
    *,
    config: _TempConfig | None = None,
    capture_func: Callable[[CameraInfo], Any] | None = None,
) -> CaptureEngine:
    config = config or _temp_config(root, name, with_initial_config=False)
    return CaptureEngine(
        experiments_dir=root / name / "experiments",
        cameras_path=config.cameras_path,
        state_path=config.state_path,
        capture_func=capture_func or _capture_ok,
        preview_func=capture_func or _capture_ok,
        camera_check_func=_camera_check_ok,
        detected_camera_func=_detected_cameras,
        detected_preview_func=_preview_detected_ok,
        save_jpeg_func=_save_jpeg,
        disk_usage_func=_disk_usage,
        poll_floor_seconds=0.05,
    )


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
            identity_strategy="index_fallback",
            stable_id="1",
            index=1,
            warnings=[
                "index fallback - OpenCV index only; not durable across reboots or replugging"
            ],
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


if __name__ == "__main__":
    raise SystemExit(main())
