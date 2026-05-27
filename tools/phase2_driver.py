#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labcam.cameras.interface import CameraInfo, capture_frame
from labcam.engine import BaselineCaptureError, CaptureEngine, DiskSpaceError, ExperimentConfig
from labcam.engine.state import RunningStateManager
from labcam.engine.storage import (
    append_log_line,
    atomic_write_json,
    build_metadata,
    create_experiment_paths,
    local_now,
    read_json_file,
)


ONE_PIXEL_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////"
    "2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/"
    "xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIQAxAAAAH/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAEFAqf/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAEDAQE/ASP/"
    "xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oACAECAQE/ASP/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAY/Al//xAAUEAEAAAAAAAAAAAAAAAAAAAAA/9oACAEBAAE/IV//2gAMAwEA"
    "AgADAAAAEP/EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8QH//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8QH//EABQQAQAAAAAAAAAAAAAAAAAAABD/2gAIAQEAAT8QH//Z"
)


@dataclass(frozen=True)
class Profile:
    duration_hours: float
    interval_minutes: float
    timeout_seconds: float
    poll_floor_seconds: float


PROFILES = {
    "fast": Profile(
        duration_hours=5 / 3600,
        interval_minutes=1 / 60,
        timeout_seconds=20,
        poll_floor_seconds=0.1,
    ),
    "spec": Profile(
        duration_hours=2 / 60,
        interval_minutes=20 / 60,
        timeout_seconds=180,
        poll_floor_seconds=1.0,
    ),
}


class ScenarioFailure(RuntimeError):
    pass


@dataclass
class CaptureProvider:
    mock: bool
    trace_inside_capture: bool = False

    def capture(self, camera: CameraInfo) -> Any:
        if self.mock:
            return ONE_PIXEL_JPEG
        return capture_frame(camera)

    def save_jpeg(self, image: Any, output_path: Path, *, quality: int | None = None) -> Path:
        if self.mock:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image if isinstance(image, bytes) else ONE_PIXEL_JPEG)
            return output_path.resolve()
        from labcam.cameras.interface import save_jpeg

        return save_jpeg(image, output_path, quality=quality)

    def can_trace_capture_window(self) -> bool:
        return self.mock or self.trace_inside_capture


def main() -> int:
    parser = argparse.ArgumentParser(description="Exercise Phase 2 capture-engine scenarios.")
    parser.add_argument("--cameras", nargs="+", default=["station1", "station2"])
    parser.add_argument("--experiments-dir", type=Path)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="fast")
    parser.add_argument(
        "--mock-capture",
        action="store_true",
        help="Use deterministic fake JPEG captures instead of opening real cameras.",
    )
    args = parser.parse_args()

    profile = PROFILES[args.profile]
    provider = CaptureProvider(mock=args.mock_capture)
    experiments_dir = (
        args.experiments_dir.resolve()
        if args.experiments_dir
        else Path(tempfile.mkdtemp(prefix="labcam-phase2-driver-")).resolve()
    )
    state_path = experiments_dir / "running_state.json"
    results: list[tuple[str, bool, str]] = []

    scenarios: list[tuple[str, Callable[[], str]]] = [
        (
            "single experiment",
            lambda: scenario_single_experiment(args.cameras[0], experiments_dir, state_path, profile, provider),
        ),
        (
            "two concurrent experiments",
            lambda: scenario_two_concurrent(args.cameras, experiments_dir, state_path, profile, provider),
        ),
        (
            "induced capture failure",
            lambda: scenario_induced_failure(args.cameras[0], experiments_dir, state_path, profile, provider),
        ),
        (
            "baseline failure",
            lambda: scenario_baseline_failure(experiments_dir),
        ),
        (
            "crash recovery",
            lambda: scenario_crash_recovery(experiments_dir),
        ),
        (
            "disk-space preflight",
            lambda: scenario_disk_preflight(experiments_dir),
        ),
    ]

    capture_mode = "mock" if args.mock_capture else "real"
    print(
        f"Phase 2 driver profile={args.profile} capture={capture_mode} "
        f"experiments_dir={experiments_dir}"
    )
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
        status = "PASS" if ok else "FAIL"
        print(f"- {status} {name}: {detail}")

    return 0 if passed == len(results) else 1


def scenario_single_experiment(
    camera_label: str,
    experiments_dir: Path,
    state_path: Path,
    profile: Profile,
    provider: CaptureProvider,
) -> str:
    engine = CaptureEngine(
        experiments_dir=experiments_dir,
        state_path=state_path,
        capture_func=provider.capture,
        save_jpeg_func=provider.save_jpeg,
        poll_floor_seconds=profile.poll_floor_seconds,
    )
    try:
        experiment_id = engine.start_experiment(
            ExperimentConfig(
                name="phase2-single",
                camera_label=camera_label,
                interval_minutes=profile.interval_minutes,
                duration_hours=profile.duration_hours,
                operator="phase2-driver",
            )
        )
        _wait_finished(engine, profile.timeout_seconds)
        folder = experiments_dir / experiment_id
        _assert_completed_folder(folder, min_images=3)
        _assert_state_empty(state_path)
        return str(folder)
    finally:
        engine.shutdown()


def scenario_two_concurrent(
    camera_labels: list[str],
    experiments_dir: Path,
    state_path: Path,
    profile: Profile,
    provider: CaptureProvider,
) -> str:
    if len(camera_labels) < 2:
        raise ScenarioFailure("two camera labels are required")

    trace: list[tuple[str, datetime, datetime]] = []

    def traced_capture(camera: CameraInfo) -> Any:
        if not provider.can_trace_capture_window():
            return provider.capture(camera)
        started = local_now()
        frame = provider.capture(camera)
        ended = local_now()
        trace.append((camera.label, started, ended))
        return frame

    engine = CaptureEngine(
        experiments_dir=experiments_dir,
        state_path=state_path,
        capture_func=traced_capture,
        save_jpeg_func=provider.save_jpeg,
        poll_floor_seconds=profile.poll_floor_seconds,
    )
    try:
        first = engine.start_experiment(
            ExperimentConfig(
                name="phase2-concurrent-a",
                camera_label=camera_labels[0],
                interval_minutes=profile.interval_minutes,
                duration_hours=profile.duration_hours,
                operator="phase2-driver",
            )
        )
        second = engine.start_experiment(
            ExperimentConfig(
                name="phase2-concurrent-b",
                camera_label=camera_labels[1],
                interval_minutes=profile.interval_minutes,
                duration_hours=profile.duration_hours,
                operator="phase2-driver",
            )
        )
        _wait_finished(engine, profile.timeout_seconds)
        _assert_completed_folder(experiments_dir / first, min_images=3)
        _assert_completed_folder(experiments_dir / second, min_images=3)
        if trace:
            _assert_no_capture_overlap(trace)
        _assert_state_empty(state_path)
        return f"{experiments_dir / first}, {experiments_dir / second}"
    finally:
        engine.shutdown()


def scenario_induced_failure(
    camera_label: str,
    experiments_dir: Path,
    state_path: Path,
    profile: Profile,
    provider: CaptureProvider,
) -> str:
    calls = 0
    failures_remaining = 0

    def flaky_capture(camera: CameraInfo) -> Any:
        nonlocal calls, failures_remaining
        calls += 1
        if calls > 1 and failures_remaining > 0:
            failures_remaining -= 1
            raise RuntimeError("induced capture failure")
        return provider.capture(camera)

    engine = CaptureEngine(
        experiments_dir=experiments_dir,
        state_path=state_path,
        capture_func=flaky_capture,
        save_jpeg_func=provider.save_jpeg,
        poll_floor_seconds=profile.poll_floor_seconds,
    )
    failures_remaining = engine.capture_retries + 1
    try:
        experiment_id = engine.start_experiment(
            ExperimentConfig(
                name="phase2-induced-failure",
                camera_label=camera_label,
                interval_minutes=profile.interval_minutes,
                duration_hours=max(profile.duration_hours, 6 / 3600),
                operator="phase2-driver",
            )
        )
        _wait_finished(engine, max(profile.timeout_seconds, 20))
        folder = experiments_dir / experiment_id
        log_text = (folder / "capture_log.txt").read_text(encoding="utf-8")
        if "failed after retries; sequence gap recorded" not in log_text:
            raise ScenarioFailure("missing scheduled-failure gap log")
        images = sorted((folder / "images").glob("*.jpg"))
        names = {image.name[:4] for image in images}
        if "0001" in names or "0002" not in names:
            raise ScenarioFailure("expected sequence 0001 gap followed by sequence 0002")
        _assert_completed_folder(folder, min_images=2)
        _assert_state_empty(state_path)
        return str(folder)
    finally:
        engine.shutdown()


def scenario_baseline_failure(experiments_dir: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="labcam-phase2-baseline-") as temp:
        temp_path = Path(temp)
        cameras_path = _write_temp_cameras(temp_path, "missing-station", 9999)
        state_path = temp_path / "running_state.json"

        def always_fail(_: CameraInfo) -> Any:
            raise RuntimeError("baseline camera unavailable")

        engine = CaptureEngine(
            experiments_dir=experiments_dir,
            cameras_path=cameras_path,
            state_path=state_path,
            capture_func=always_fail,
            save_jpeg_func=CaptureProvider(mock=True).save_jpeg,
            poll_floor_seconds=0.1,
        )
        try:
            try:
                engine.start_experiment(
                    ExperimentConfig(
                        name="phase2-baseline-failure",
                        camera_label="missing-station",
                        interval_minutes=1,
                        duration_hours=1,
                    )
                )
            except BaselineCaptureError:
                pass
            else:
                raise ScenarioFailure("baseline failure did not raise BaselineCaptureError")

            folders = sorted(experiments_dir.glob("*phase2-baseline-failure_missing-station*"))
            if not folders:
                raise ScenarioFailure("baseline failure folder was not retained")
            folder = folders[-1]
            metadata = read_json_file(folder / "metadata.json")
            if metadata.get("end_reason") != "baseline_failed" or metadata.get("images_captured") != 0:
                raise ScenarioFailure("baseline failure metadata was not finalized")
            _assert_state_empty(state_path)
            return str(folder)
        finally:
            engine.shutdown()


def scenario_crash_recovery(experiments_dir: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="labcam-phase2-recovery-") as temp:
        temp_path = Path(temp)
        state_path = temp_path / "running_state.json"
        started_at = local_now()
        paths = create_experiment_paths(
            experiments_dir=experiments_dir,
            experiment_name="phase2-crash-recovery",
            camera_label="station-recovery",
            started_at=started_at,
        )
        metadata = build_metadata(
            name="phase2-crash-recovery",
            camera_label="station-recovery",
            camera_id="recovery",
            camera_identity_strategy="index_fallback",
            interval_minutes=1,
            duration_hours=1,
            operator="phase2-driver",
            notes="seeded stale state",
            started_at=started_at,
            planned_stop_at=started_at + timedelta(hours=1),
            images_captured=1,
        )
        atomic_write_json(paths.metadata_path, metadata)
        append_log_line(paths.log_path, started_at, "START", "experiment=phase2-crash-recovery camera=station-recovery interval=1min duration=1h")
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
        metadata = read_json_file(paths.metadata_path)
        if metadata.get("end_reason") != "unknown":
            raise ScenarioFailure("crash recovery did not mark metadata unknown")
        _assert_state_empty(state_path)
        return str(paths.root)


def scenario_disk_preflight(experiments_dir: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="labcam-phase2-disk-") as temp:
        temp_path = Path(temp)
        cameras_path = _write_temp_cameras(temp_path, "disk-station", 0)
        state_path = temp_path / "running_state.json"

        def no_space(_: Path) -> shutil._ntuple_diskusage:
            return shutil._ntuple_diskusage(total=100, used=100, free=0)

        engine = CaptureEngine(
            experiments_dir=experiments_dir,
            cameras_path=cameras_path,
            state_path=state_path,
            disk_usage_func=no_space,
            poll_floor_seconds=0.1,
        )
        try:
            try:
                engine.start_experiment(
                    ExperimentConfig(
                        name="phase2-disk-preflight",
                        camera_label="disk-station",
                        interval_minutes=1,
                        duration_hours=24,
                    )
                )
            except DiskSpaceError:
                return "start failed fast with DiskSpaceError"
            raise ScenarioFailure("disk preflight did not raise DiskSpaceError")
        finally:
            engine.shutdown()


def _wait_finished(engine: CaptureEngine, timeout_seconds: float) -> None:
    if not engine.wait_until_idle(timeout_seconds=timeout_seconds):
        raise ScenarioFailure("engine did not finish before timeout")


def _assert_completed_folder(folder: Path, *, min_images: int) -> None:
    metadata = read_json_file(folder / "metadata.json")
    if metadata.get("end_reason") != "completed":
        raise ScenarioFailure(f"{folder} did not complete")
    images = sorted((folder / "images").glob("*.jpg"))
    if len(images) < min_images:
        raise ScenarioFailure(f"{folder} has only {len(images)} image(s)")
    if not images[0].name.startswith("0000_"):
        raise ScenarioFailure(f"{folder} missing baseline 0000 image")
    log_text = (folder / "capture_log.txt").read_text(encoding="utf-8")
    for token in ("START", "CAPTURE", "STOP"):
        if token not in log_text:
            raise ScenarioFailure(f"{folder} log missing {token}")


def _assert_state_empty(state_path: Path) -> None:
    state = read_json_file(state_path)
    if state.get("running") != []:
        raise ScenarioFailure(f"{state_path} is not empty")


def _assert_no_capture_overlap(trace: list[tuple[str, datetime, datetime]]) -> None:
    ordered = sorted(trace, key=lambda item: item[1])
    for previous, current in zip(ordered, ordered[1:]):
        if current[1] < previous[2]:
            raise ScenarioFailure(
                f"capture overlap: {previous[0]} ended {previous[2]}, "
                f"{current[0]} started {current[1]}"
            )


def _write_temp_cameras(root: Path, label: str, index: int) -> Path:
    cameras_path = root / "cameras.json"
    cameras_path.write_text(
        json.dumps(
            {
                "cameras": [
                    {
                        "label": label,
                        "identity_strategy": "index_fallback",
                        "stable_id": str(index),
                        "last_seen_index": index,
                        "warnings": [],
                        "notes": "phase2 driver temporary camera",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return cameras_path


if __name__ == "__main__":
    raise SystemExit(main())
