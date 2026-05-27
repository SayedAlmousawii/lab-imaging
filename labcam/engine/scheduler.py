from __future__ import annotations

import json
import math
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from labcam.cameras.interface import CameraInfo, capture_frame, save_jpeg
from labcam.engine.experiment import (
    ActiveExperimentError,
    BaselineCaptureError,
    CameraConfigError,
    DiskSpaceError,
    EngineError,
    Experiment,
    ExperimentConfig,
    ExperimentNotFoundError,
)
from labcam.engine.state import DEFAULT_STATE_PATH, RunningStateManager
from labcam.engine.storage import (
    DEFAULT_EXPERIMENTS_DIR,
    DEFAULT_JPEG_QUALITY,
    append_log_line,
    build_metadata,
    create_experiment_paths,
    local_now,
    save_frame_as_jpeg,
    update_metadata_finalize,
    write_metadata,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"
DEFAULT_CAMERAS_PATH = PROJECT_ROOT / "config" / "cameras.json"
DEFAULT_CAPTURE_RETRIES = 2
CONSERVATIVE_BYTES_PER_IMAGE = 8_000_000


@dataclass(frozen=True)
class CameraRecord:
    label: str
    identity_strategy: str
    stable_id: str
    last_seen_index: int
    warnings: list[str]

    def to_camera_info(self) -> CameraInfo:
        return CameraInfo(
            label=self.label,
            identity_strategy=self.identity_strategy,  # type: ignore[arg-type]
            stable_id=self.stable_id,
            index=self.last_seen_index,
            warnings=self.warnings,
        )


class CaptureEngine:
    def __init__(
        self,
        *,
        experiments_dir: Path | None = None,
        settings_path: Path = DEFAULT_SETTINGS_PATH,
        cameras_path: Path = DEFAULT_CAMERAS_PATH,
        state_path: Path = DEFAULT_STATE_PATH,
        capture_func: Callable[[CameraInfo], Any] = capture_frame,
        save_jpeg_func: Callable[..., Path] = save_jpeg,
        disk_usage_func: Callable[[Path], shutil._ntuple_diskusage] = shutil.disk_usage,
        now_func: Callable[[], datetime] = local_now,
        poll_floor_seconds: float = 1.0,
        recover_stale: bool = True,
    ) -> None:
        self.settings_path = settings_path
        self.cameras_path = cameras_path
        self.settings = self._load_settings()
        self.experiments_dir = (
            Path(experiments_dir)
            if experiments_dir is not None
            else Path(self.settings.get("experiments_dir", DEFAULT_EXPERIMENTS_DIR))
        )
        if not self.experiments_dir.is_absolute():
            self.experiments_dir = PROJECT_ROOT / self.experiments_dir
        self.experiments_dir = self.experiments_dir.resolve()
        self.state = RunningStateManager(state_path)
        self.capture_func = capture_func
        self.save_jpeg_func = save_jpeg_func
        self.disk_usage_func = disk_usage_func
        self.now_func = now_func
        self.poll_floor_seconds = poll_floor_seconds
        self.capture_retries = int(self.settings.get("capture_retries", DEFAULT_CAPTURE_RETRIES))
        self.jpeg_quality = int(self.settings.get("jpeg_quality", DEFAULT_JPEG_QUALITY))
        self._active: dict[str, Experiment] = {}
        self._finished: dict[str, Experiment] = {}
        self._starting_cameras: set[str] = set()
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None

        if recover_stale:
            self.state.recover_startup(
                experiments_dir=self.experiments_dir,
                startup_time=self.now_func(),
            )

    def start_experiment(self, config: ExperimentConfig | dict[str, Any]) -> str:
        experiment_config = (
            config if isinstance(config, ExperimentConfig) else ExperimentConfig(**config)
        )
        experiment_config.validate()
        camera = self._camera_record(experiment_config.camera_label)
        self._reserve_camera(camera.label)

        try:
            self._check_disk_space(experiment_config)

            started_at = self.now_func()
            planned_stop_at = started_at + timedelta(hours=experiment_config.duration_hours)
            paths = create_experiment_paths(
                experiments_dir=self.experiments_dir,
                experiment_name=experiment_config.name,
                camera_label=experiment_config.camera_label,
                started_at=started_at,
            )
            experiment = Experiment(
                config=experiment_config,
                camera_id=camera.stable_id,
                camera_identity_strategy=camera.identity_strategy,
                paths=paths,
                started_at=started_at,
                planned_stop_at=planned_stop_at,
            )
            metadata = build_metadata(
                name=experiment_config.name,
                camera_label=experiment_config.camera_label,
                camera_id=camera.stable_id,
                camera_identity_strategy=camera.identity_strategy,
                interval_minutes=experiment_config.interval_minutes,
                duration_hours=experiment_config.duration_hours,
                operator=experiment_config.operator,
                notes=experiment_config.notes,
                started_at=started_at,
                planned_stop_at=planned_stop_at,
            )
            write_metadata(paths, metadata)
            append_log_line(
                paths.log_path,
                started_at,
                "START",
                (
                    f"experiment={metadata['name']} camera={experiment_config.camera_label} "
                    f"interval={_format_minutes(experiment_config.interval_minutes)} "
                    f"duration={_format_hours(experiment_config.duration_hours)}"
                ),
            )

            try:
                self._capture_sequence(
                    experiment=experiment,
                    camera=camera,
                    sequence=0,
                    scheduled_at=started_at,
                )
            except Exception as exc:
                failed_at = self.now_func()
                experiment.finalize("baseline_failed", failed_at)
                update_metadata_finalize(
                    paths.metadata_path,
                    ended_at=failed_at,
                    end_reason="baseline_failed",
                    images_captured=0,
                )
                append_log_line(paths.log_path, failed_at, "STOP", "reason=baseline_failed images=0")
                raise BaselineCaptureError(
                    f"Baseline capture failed for {experiment_config.camera_label}: {exc}"
                ) from exc

            experiment.record_success()
            experiment.sequence = 1
            experiment.start()

            with self._lock:
                self._starting_cameras.discard(camera.label)
                self._active[experiment.experiment_id] = experiment
                self.state.replace_entry(experiment.to_running_state())
                self._ensure_thread()
                self._wake.set()

            return experiment.experiment_id
        except Exception:
            with self._lock:
                self._starting_cameras.discard(camera.label)
            raise

    def stop_experiment(self, experiment_id: str) -> None:
        with self._lock:
            experiment = self._active.get(experiment_id)
            if experiment is None:
                raise ExperimentNotFoundError(f"Unknown running experiment: {experiment_id}")
            experiment.stop_requested = True
            self._wake.set()

    def list_experiments(self) -> list[dict[str, object]]:
        with self._lock:
            experiments = list(self._active.values()) + list(self._finished.values())
            return [experiment.to_status() for experiment in experiments]

    def latest_frame_path(self, experiment_id: str) -> Path | None:
        with self._lock:
            experiment = self._active.get(experiment_id) or self._finished.get(experiment_id)
            if experiment is None:
                raise ExperimentNotFoundError(f"Unknown experiment: {experiment_id}")
            return experiment.latest_frame_path()

    def shutdown(self, *, wait: bool = True) -> None:
        self._shutdown.set()
        self._wake.set()
        thread = self._thread
        if wait and thread is not None:
            thread.join(timeout=5)

    def wait_until_idle(self, *, timeout_seconds: float | None = None) -> bool:
        deadline = None if timeout_seconds is None else self.now_func() + timedelta(seconds=timeout_seconds)
        while True:
            with self._lock:
                if not self._active:
                    return True
            if deadline is not None and self.now_func() >= deadline:
                return False
            self._wake.wait(0.2)
            self._wake.clear()

    def _run_loop(self) -> None:
        while not self._shutdown.is_set():
            due: list[Experiment] = []
            finalize_completed: list[Experiment] = []
            finalize_stopped: list[Experiment] = []
            sleep_seconds = self.poll_floor_seconds
            now = self.now_func()

            with self._lock:
                for experiment in self._active.values():
                    if experiment.stop_requested:
                        finalize_stopped.append(experiment)
                        continue
                    if experiment.tick(now):
                        due.append(experiment)
                        continue
                    if now >= experiment.planned_stop_at:
                        finalize_completed.append(experiment)
                        continue
                    if experiment.next_capture_at is not None:
                        seconds_until_due = (experiment.next_capture_at - now).total_seconds()
                        sleep_seconds = min(sleep_seconds, max(0.01, seconds_until_due))

            for experiment in finalize_stopped:
                self._finalize(experiment.experiment_id, "stopped_early")
            for experiment in sorted(due, key=lambda item: item.next_capture_at or item.started_at):
                self._run_scheduled_capture(experiment.experiment_id)
            for experiment in finalize_completed:
                self._finalize(experiment.experiment_id, "completed")

            self._wake.wait(sleep_seconds)
            self._wake.clear()

    def _run_scheduled_capture(self, experiment_id: str) -> None:
        with self._lock:
            experiment = self._active.get(experiment_id)
            if experiment is None or experiment.next_capture_at is None:
                return
            camera = self._camera_record(experiment.config.camera_label)
            sequence = experiment.sequence
            scheduled_at = experiment.next_capture_at

        success = False
        try:
            self._capture_sequence(
                experiment=experiment,
                camera=camera,
                sequence=sequence,
                scheduled_at=scheduled_at,
            )
            success = True
        except Exception:
            pass

        with self._lock:
            active = self._active.get(experiment_id)
            if active is None:
                return
            if success:
                active.record_success()
            active.advance_after_attempt()
            self.state.replace_entry(active.to_running_state())
            if active.next_capture_at and active.next_capture_at > active.planned_stop_at:
                self._finalize(active.experiment_id, "completed")

    def _capture_sequence(
        self,
        *,
        experiment: Experiment,
        camera: CameraRecord,
        sequence: int,
        scheduled_at: datetime,
    ) -> None:
        attempts = self.capture_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                frame = self.capture_func(camera.to_camera_info())
                captured_at = self.now_func()
                image_path = save_frame_as_jpeg(
                    image=frame,
                    paths=experiment.paths,
                    sequence=sequence,
                    captured_at=scheduled_at,
                    jpeg_quality=self.jpeg_quality,
                    save_jpeg_func=self.save_jpeg_func,
                )
                append_log_line(
                    experiment.paths.log_path,
                    captured_at,
                    "CAPTURE",
                    f"seq={sequence:04d} file={image_path.name} ok",
                )
                return
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    append_log_line(
                        experiment.paths.log_path,
                        self.now_func(),
                        "ERROR",
                        f"seq={sequence:04d} {exc}, retry {attempt}",
                    )

        append_log_line(
            experiment.paths.log_path,
            self.now_func(),
            "ERROR",
            f"seq={sequence:04d} failed after retries; sequence gap recorded",
        )
        raise EngineError(str(last_error) if last_error else "capture failed")

    def _finalize(self, experiment_id: str, reason: str) -> None:
        with self._lock:
            experiment = self._active.pop(experiment_id, None)
            if experiment is None:
                return
            ended_at = self.now_func()
            experiment.finalize(reason, ended_at)
            update_metadata_finalize(
                experiment.paths.metadata_path,
                ended_at=ended_at,
                end_reason=reason,
                images_captured=experiment.images_captured,
            )
            append_log_line(
                experiment.paths.log_path,
                ended_at,
                "STOP",
                f"reason={reason} images={experiment.images_captured}",
            )
            self.state.remove_entry(experiment.experiment_id)
            self._finished[experiment.experiment_id] = experiment
            self._wake.set()

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="labcam-capture-engine", daemon=True)
        self._thread.start()

    def _ensure_camera_is_available(self, camera_label: str) -> None:
        with self._lock:
            if camera_label in self._starting_cameras:
                raise ActiveExperimentError(
                    f"Camera {camera_label} already has a starting experiment"
                )
            for experiment in self._active.values():
                if experiment.config.camera_label == camera_label:
                    raise ActiveExperimentError(
                        f"Camera {camera_label} already has a running experiment"
                    )

    def _reserve_camera(self, camera_label: str) -> None:
        with self._lock:
            self._ensure_camera_is_available(camera_label)
            self._starting_cameras.add(camera_label)

    def _check_disk_space(self, config: ExperimentConfig) -> None:
        expected_images = math.ceil((config.duration_hours * 60) / config.interval_minutes) + 2
        required = expected_images * CONSERVATIVE_BYTES_PER_IMAGE
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        free = self.disk_usage_func(self.experiments_dir).free
        if free < required:
            raise DiskSpaceError(
                f"Insufficient free space for {expected_images} images: "
                f"need about {required} bytes, have {free} bytes"
            )

    def _camera_record(self, camera_label: str) -> CameraRecord:
        cameras = self._load_cameras()
        for item in cameras:
            if item.label == camera_label:
                return item
        labels = ", ".join(camera.label for camera in cameras) or "none"
        raise CameraConfigError(f"Unknown camera label {camera_label!r}; configured labels: {labels}")

    def _load_cameras(self) -> list[CameraRecord]:
        if not self.cameras_path.exists():
            raise CameraConfigError(
                f"Missing {self.cameras_path}; run tools/camera_setup.py setup first"
            )
        with self.cameras_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        records = payload.get("cameras")
        if not isinstance(records, list):
            raise CameraConfigError(f"Expected cameras list in {self.cameras_path}")

        cameras: list[CameraRecord] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            cameras.append(
                CameraRecord(
                    label=str(record["label"]),
                    identity_strategy=str(record["identity_strategy"]),
                    stable_id=str(record["stable_id"]),
                    last_seen_index=int(record["last_seen_index"]),
                    warnings=list(record.get("warnings") or []),
                )
            )
        return cameras

    def _load_settings(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            return {}
        with self.settings_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            raise EngineError(f"Expected settings object in {self.settings_path}")
        return payload


def _format_minutes(value: float) -> str:
    return f"{int(value)}min" if float(value).is_integer() else f"{value:g}min"


def _format_hours(value: float) -> str:
    return f"{int(value)}h" if float(value).is_integer() else f"{value:g}h"
