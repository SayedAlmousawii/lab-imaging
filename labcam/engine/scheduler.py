from __future__ import annotations

import errno
import json
import math
import re
import shutil
import threading
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from labcam.cameras.interface import (
    CameraInfo,
    capture_frame,
    check_camera_available,
    list_cameras_fresh_process as detect_camera_infos,
    preview_camera_fresh_process,
    preview_frame,
    save_jpeg,
)
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
    atomic_write_json,
    build_metadata,
    create_experiment_paths,
    iso_timestamp,
    local_now,
    save_frame_as_jpeg,
    update_metadata_finalize,
    write_metadata,
    StorageError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"
DEFAULT_CAMERAS_PATH = PROJECT_ROOT / "config" / "cameras.json"
DEFAULT_CAPTURE_RETRIES = 2
CONSERVATIVE_BYTES_PER_IMAGE = 8_000_000
LOW_FREE_BYTES = 1_000_000
CAMERA_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


class _TerminalStorageFailure(RuntimeError):
    def __init__(self, *, reason: str, message: str, image_saved: bool = False) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.image_saved = image_saved


@dataclass(frozen=True)
class CameraRecord:
    label: str
    identity_strategy: str
    stable_id: str
    last_seen_index: int
    warnings: list[str]
    notes: str = ""
    last_confirmed_at: str | None = None
    last_confirmed_index: int | None = None

    def to_camera_info(self) -> CameraInfo:
        return CameraInfo(
            label=self.label,
            identity_strategy=self.identity_strategy,  # type: ignore[arg-type]
            stable_id=self.stable_id,
            index=self.last_seen_index,
            warnings=self.warnings,
        )


class _CaptureMarker:
    def __init__(self, engine: "CaptureEngine", camera_label: str) -> None:
        self.engine = engine
        self.camera_label = camera_label

    def __enter__(self) -> None:
        with self.engine._lock:
            self.engine._capturing_cameras[self.camera_label] = (
                self.engine._capturing_cameras.get(self.camera_label, 0) + 1
            )

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        with self.engine._lock:
            self.engine._unmark_capturing(self.camera_label)


class CaptureEngine:
    def __init__(
        self,
        *,
        experiments_dir: Path | None = None,
        settings_path: Path = DEFAULT_SETTINGS_PATH,
        cameras_path: Path = DEFAULT_CAMERAS_PATH,
        state_path: Path = DEFAULT_STATE_PATH,
        capture_func: Callable[[CameraInfo], Any] = capture_frame,
        preview_func: Callable[[CameraInfo], Any] = preview_frame,
        camera_check_func: Callable[[CameraInfo], None] = check_camera_available,
        detected_camera_func: Callable[[], list[CameraInfo]] = detect_camera_infos,
        detected_preview_func: Callable[..., Path] = preview_camera_fresh_process,
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
        self.preview_func = preview_func
        self.camera_check_func = camera_check_func
        self.detected_camera_func = detected_camera_func
        self.detected_preview_func = detected_preview_func
        self.save_jpeg_func = save_jpeg_func
        self.disk_usage_func = disk_usage_func
        self.now_func = now_func
        self.poll_floor_seconds = poll_floor_seconds
        self.capture_retries = int(self.settings.get("capture_retries", DEFAULT_CAPTURE_RETRIES))
        self.jpeg_quality = int(self.settings.get("jpeg_quality", DEFAULT_JPEG_QUALITY))
        self._active: dict[str, Experiment] = {}
        self._finished: dict[str, Experiment] = {}
        self._starting_cameras: set[str] = set()
        self._capturing_cameras: dict[str, int] = {}
        self._verified_camera_labels: set[str] = set()
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
        self._ensure_camera_verified(camera.label)
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
                    f"Baseline capture failed for {experiment_config.camera_label}. "
                    f"{_capture_error_message(exc)}"
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

    def start(self) -> None:
        with self._lock:
            self._ensure_thread()

    def list_cameras(self) -> list[CameraRecord]:
        return self._load_cameras()

    def detected_cameras(self) -> list[dict[str, Any]]:
        self._ensure_camera_setup_idle()
        return [self._detected_camera_payload(camera) for camera in self.detected_camera_func()]

    def preview_detected_camera(self, camera_index: int, *, output_dir: Path | None = None) -> Path:
        self._ensure_camera_setup_idle()
        camera = self._detected_camera(camera_index)
        self._ensure_detected_camera_not_busy(camera.index)
        preview_dir = Path(output_dir) if output_dir is not None else Path(tempfile.gettempdir())
        preview_dir.mkdir(parents=True, exist_ok=True)
        output_path = preview_dir / f"labcam-preview-detected-{camera.index}.jpg"
        return self.detected_preview_func(camera.index, output_path, quality=self.jpeg_quality)

    def save_camera_config(self, mappings: list[dict[str, Any]]) -> dict[str, Any]:
        self._ensure_camera_setup_idle()
        detected_by_index = {camera.index: camera for camera in self.detected_camera_func()}
        if not mappings:
            raise CameraConfigError("At least one camera mapping is required.")

        records: list[dict[str, Any]] = []
        labels: set[str] = set()
        indexes: set[int] = set()
        for position, mapping in enumerate(mappings, start=1):
            label = str(mapping.get("label") or "").strip()
            if not CAMERA_LABEL_PATTERN.fullmatch(label):
                raise CameraConfigError(
                    "Station labels may use only letters, numbers, and hyphens."
                )
            if label in labels:
                raise CameraConfigError(f"Duplicate station label: {label}")
            labels.add(label)

            try:
                camera_index = int(mapping.get("camera_index"))
            except (TypeError, ValueError) as exc:
                raise CameraConfigError(f"Camera index is required for mapping {position}.") from exc
            if camera_index in indexes:
                raise CameraConfigError(f"Camera index {camera_index} is assigned more than once.")
            indexes.add(camera_index)

            detected = detected_by_index.get(camera_index)
            if detected is None:
                raise CameraConfigError(f"Camera index {camera_index} is not detected.")

            notes = str(mapping.get("notes") or "").strip()
            record: dict[str, Any] = {
                "label": label,
                "identity_strategy": detected.identity_strategy,
                "stable_id": detected.stable_id,
                "last_seen_index": detected.index,
                "warnings": detected.warnings,
            }
            if notes:
                record["notes"] = notes
            records.append(record)

        atomic_write_json(self.cameras_path, {"cameras": records})
        with self._lock:
            self._verified_camera_labels.clear()
        return self.verification_status()

    def stress_test_cameras(self, camera_indexes: list[int], *, cycles: int = 100) -> dict[str, Any]:
        self._ensure_camera_setup_idle()
        if cycles < 1:
            raise CameraConfigError("cycles must be at least 1")
        if not camera_indexes:
            raise CameraConfigError("At least one camera is required for stress test.")

        detected_by_index = {camera.index: camera for camera in self.detected_camera_func()}
        results: list[dict[str, Any]] = []
        for camera_index in camera_indexes:
            camera = detected_by_index.get(int(camera_index))
            if camera is None:
                raise CameraConfigError(f"Camera index {camera_index} is not detected.")
            self._ensure_detected_camera_not_busy(camera.index)

            failures: list[str] = []
            passed = 0
            for cycle in range(1, cycles + 1):
                try:
                    self.capture_func(camera)
                except Exception as exc:
                    failures.append(f"cycle {cycle}: {_capture_error_message(exc)}")
                    break
                passed += 1

            results.append(
                {
                    **self._detected_camera_payload(camera),
                    "cycles": cycles,
                    "passed": passed,
                    "ok": passed == cycles and not failures,
                    "failures": failures,
                }
            )

        return {"cycles": cycles, "results": results}

    def verification_required(self) -> bool:
        cameras = self._load_cameras()
        labels = {camera.label for camera in cameras}
        with self._lock:
            self._verified_camera_labels.intersection_update(labels)
            return bool(labels) and self._verified_camera_labels != labels

    def verification_status(self) -> dict[str, Any]:
        cameras = self._load_cameras()
        labels = {camera.label for camera in cameras}
        with self._lock:
            self._verified_camera_labels.intersection_update(labels)
            verified = set(self._verified_camera_labels)

        return {
            "required": bool(labels) and verified != labels,
            "complete": bool(labels) and verified == labels,
            "cameras": [
                {
                    "label": camera.label,
                    "identity_strategy": camera.identity_strategy,
                    "stable_id": camera.stable_id,
                    "last_seen_index": camera.last_seen_index,
                    "warnings": camera.warnings,
                    "identity_warning": camera.identity_strategy != "hardware_id",
                    "last_confirmed_at": camera.last_confirmed_at,
                    "last_confirmed_index": camera.last_confirmed_index,
                    "confirmed": camera.label in verified,
                }
                for camera in cameras
            ],
        }

    def confirm_camera(self, camera_label: str) -> dict[str, Any]:
        camera = self._camera_record(camera_label)
        self._capture_preview_frame(camera)
        confirmed_at = self.now_func()
        confirmed_at_iso = iso_timestamp(confirmed_at)

        payload = self._load_camera_config_payload()
        records = payload.get("cameras")
        if not isinstance(records, list):
            raise CameraConfigError(f"Expected cameras list in {self.cameras_path}")

        updated = False
        for record in records:
            if isinstance(record, dict) and str(record.get("label")) == camera.label:
                record["last_confirmed_at"] = confirmed_at_iso
                record["last_confirmed_index"] = camera.last_seen_index
                updated = True
                break
        if not updated:
            raise CameraConfigError(f"Unknown camera label {camera.label!r}")

        atomic_write_json(self.cameras_path, payload)
        with self._lock:
            self._verified_camera_labels.add(camera.label)
        return self.verification_status()

    def preview(self, camera_label: str, *, output_dir: Path | None = None) -> Path:
        camera = self._camera_record(camera_label)
        frame = self._capture_preview_frame(camera)
        preview_dir = Path(output_dir) if output_dir is not None else Path(tempfile.gettempdir())
        preview_dir.mkdir(parents=True, exist_ok=True)
        safe_label = "".join(
            char if char.isalnum() or char in {"-", "_"} else "-"
            for char in camera.label
        ).strip("-") or "camera"
        output_path = preview_dir / f"labcam-preview-{safe_label}.jpg"
        return self.save_jpeg_func(frame, output_path, quality=self.jpeg_quality)

    def _capture_preview_frame(self, camera: CameraRecord) -> Any:
        with self._lock:
            if self._capturing_cameras.get(camera.label, 0) > 0:
                raise ActiveExperimentError(f"Camera {camera.label} is currently capturing")
            self._capturing_cameras[camera.label] = self._capturing_cameras.get(camera.label, 0) + 1

        try:
            return self.preview_func(camera.to_camera_info())
        finally:
            with self._lock:
                self._unmark_capturing(camera.label)

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

    def shutdown(self, *, wait: bool = True, timeout_seconds: float | None = 5) -> None:
        self._shutdown.set()
        self._wake.set()
        thread = self._thread
        if wait and thread is not None:
            thread.join(timeout=timeout_seconds)

    def shutdown_cleanly(self, *, wait: bool = True) -> None:
        self.shutdown(wait=wait, timeout_seconds=None)
        self._finalize_all_active("stopped_early")

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
        failed_message: str | None = None
        failed_at: datetime | None = None
        try:
            self._capture_sequence(
                experiment=experiment,
                camera=camera,
                sequence=sequence,
                scheduled_at=scheduled_at,
            )
            success = True
        except _TerminalStorageFailure as exc:
            self._finalize_storage_failure(experiment_id, exc)
            return
        except Exception as exc:
            failed_at = self.now_func()
            failed_message = _capture_error_message(exc)

        with self._lock:
            active = self._active.get(experiment_id)
            if active is None:
                return
            if success:
                active.record_success()
            elif failed_message and failed_at:
                active.record_capture_failure(message=failed_message, failed_at=failed_at)
            active.advance_after_attempt()
            try:
                self.state.replace_entry(active.to_running_state())
            except Exception as exc:
                failure = self._storage_failure(exc, active.paths.root)
                if failure is None:
                    raise
                failure.image_saved = False
                self._finalize_storage_failure(active.experiment_id, failure)
                return
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
                with self._mark_capturing(camera.label):
                    frame = self.capture_func(camera.to_camera_info())
                    captured_at = self.now_func()
                    try:
                        image_path = save_frame_as_jpeg(
                            image=frame,
                            paths=experiment.paths,
                            sequence=sequence,
                            captured_at=scheduled_at,
                            jpeg_quality=self.jpeg_quality,
                            save_jpeg_func=self.save_jpeg_func,
                        )
                    except Exception as exc:
                        failure = self._storage_failure(exc, experiment.paths.root)
                        if failure is None:
                            raise
                        raise failure from exc
                try:
                    append_log_line(
                        experiment.paths.log_path,
                        captured_at,
                        "CAPTURE",
                        f"seq={sequence:04d} file={image_path.name} ok",
                    )
                except Exception as exc:
                    failure = self._storage_failure(exc, experiment.paths.root)
                    if failure is None:
                        raise
                    failure.image_saved = True
                    raise failure from exc
                return
            except _TerminalStorageFailure:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    try:
                        append_log_line(
                            experiment.paths.log_path,
                            self.now_func(),
                            "ERROR",
                            f"seq={sequence:04d} {_capture_error_message(exc)}, retry {attempt}",
                        )
                    except Exception as log_exc:
                        failure = self._storage_failure(log_exc, experiment.paths.root)
                        if failure is None:
                            raise
                        raise failure from log_exc

        try:
            append_log_line(
                experiment.paths.log_path,
                self.now_func(),
                "ERROR",
                f"seq={sequence:04d} failed after retries; sequence gap recorded",
            )
        except Exception as exc:
            failure = self._storage_failure(exc, experiment.paths.root)
            if failure is None:
                raise
            raise failure from exc
        raise EngineError(str(last_error) if last_error else "capture failed")

    def _mark_capturing(self, camera_label: str) -> "_CaptureMarker":
        return _CaptureMarker(self, camera_label)

    def _unmark_capturing(self, camera_label: str) -> None:
        count = self._capturing_cameras.get(camera_label, 0)
        if count <= 1:
            self._capturing_cameras.pop(camera_label, None)
        else:
            self._capturing_cameras[camera_label] = count - 1

    def _finalize(self, experiment_id: str, reason: str, *, health_message: str | None = None) -> None:
        with self._lock:
            experiment = self._active.get(experiment_id)
            if experiment is None:
                return

        ended_at = self.now_func()
        experiment.finalize(reason, ended_at)
        if health_message:
            experiment.mark_terminal_health(message=health_message, failed_at=ended_at)

        metadata_updated = False
        try:
            update_metadata_finalize(
                experiment.paths.metadata_path,
                ended_at=ended_at,
                end_reason=reason,
                images_captured=experiment.images_captured,
            )
            metadata_updated = True
        except Exception as exc:
            self._record_finalization_error(experiment, f"metadata update failed: {_storage_error_message(exc)}")

        try:
            append_log_line(
                experiment.paths.log_path,
                ended_at,
                "STOP",
                f"reason={reason} images={experiment.images_captured}",
            )
        except Exception as exc:
            self._record_finalization_error(experiment, f"log update failed: {_storage_error_message(exc)}")

        try:
            self.state.remove_entry(experiment.experiment_id)
        except Exception as exc:
            self._record_finalization_error(experiment, f"running-state update failed: {_storage_error_message(exc)}")
            if reason == "stopped_early" and not metadata_updated:
                return

        with self._lock:
            self._active.pop(experiment_id, None)
            self._finished[experiment.experiment_id] = experiment
            self._wake.set()

    def _finalize_storage_failure(self, experiment_id: str, failure: _TerminalStorageFailure) -> None:
        with self._lock:
            experiment = self._active.get(experiment_id)
            if experiment is None:
                return
            if failure.image_saved:
                experiment.record_success()
            failed_at = self.now_func()
            experiment.mark_terminal_health(message=failure.message, failed_at=failed_at)

        self._safe_append_log_line(
            experiment.paths.log_path,
            failed_at,
            "ERROR",
            f"seq={experiment.sequence:04d} {failure.message}",
        )
        self._finalize(experiment_id, failure.reason, health_message=failure.message)

    def _finalize_all_active(self, reason: str) -> None:
        with self._lock:
            experiment_ids = list(self._active)
        for experiment_id in experiment_ids:
            self._finalize(experiment_id, reason)

    def _safe_append_log_line(self, log_path: Path, event_time: datetime, event: str, message: str) -> None:
        try:
            append_log_line(log_path, event_time, event, message)
        except Exception:
            pass

    def _record_finalization_error(self, experiment: Experiment, message: str) -> None:
        experiment.mark_terminal_health(message=message, failed_at=self.now_func())

    def camera_unavailable_message(self, camera: CameraRecord) -> str | None:
        with self._lock:
            if camera.label in self._starting_cameras or self._capturing_cameras.get(camera.label, 0) > 0:
                return None
        try:
            self.camera_check_func(camera.to_camera_info())
        except Exception as exc:
            return _capture_error_message(exc)
        return None

    def _detected_camera(self, camera_index: int) -> CameraInfo:
        for camera in self.detected_camera_func():
            if camera.index == camera_index:
                return camera
        raise CameraConfigError(f"Camera index {camera_index} is not detected.")

    def _detected_camera_payload(self, camera: CameraInfo) -> dict[str, Any]:
        return {
            "label": camera.label,
            "index": camera.index,
            "identity_strategy": camera.identity_strategy,
            "stable_id": camera.stable_id,
            "warnings": camera.warnings,
            "identity_warning": camera.identity_strategy != "hardware_id",
        }

    def _ensure_detected_camera_not_busy(self, camera_index: int) -> None:
        configured_by_label = {camera.label: camera for camera in self._load_cameras_if_present()}
        with self._lock:
            busy_labels = set(self._starting_cameras)
            busy_labels.update(
                label
                for label, count in self._capturing_cameras.items()
                if count > 0
            )
            busy_labels.update(experiment.config.camera_label for experiment in self._active.values())

        for label in busy_labels:
            camera = configured_by_label.get(label)
            if camera and camera.last_seen_index == camera_index:
                raise ActiveExperimentError(f"Camera {label} is currently busy")

    def _ensure_camera_setup_idle(self) -> None:
        with self._lock:
            if self._starting_cameras or self._active or any(self._capturing_cameras.values()):
                raise ActiveExperimentError(
                    "Camera setup is unavailable while experiments are running."
                )

    def _load_cameras_if_present(self) -> list[CameraRecord]:
        if not self.cameras_path.exists():
            return []
        return self._load_cameras()

    def _storage_failure(self, exc: Exception, path: Path) -> _TerminalStorageFailure | None:
        reason = self._storage_failure_reason(exc, path)
        if reason is None:
            return None
        if reason == "disk_full":
            return _TerminalStorageFailure(
                reason="disk_full",
                message="Storage is full. Free space and start a new run.",
            )
        return _TerminalStorageFailure(
            reason="storage_failed",
            message="Storage is not writable. Check the results folder and start a new run.",
        )

    def _storage_failure_reason(self, exc: Exception, path: Path) -> str | None:
        if _is_no_space_error(exc) or self._low_free_space(path):
            return "disk_full"
        if _is_storage_error(exc):
            return "storage_failed"
        return None

    def _low_free_space(self, path: Path) -> bool:
        probe = path if path.exists() else path.parent
        try:
            return self.disk_usage_func(probe).free < LOW_FREE_BYTES
        except Exception:
            return False

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

    def _ensure_camera_verified(self, camera_label: str) -> None:
        if not self.verification_required():
            return
        with self._lock:
            if camera_label in self._verified_camera_labels:
                return
        raise EngineError("Confirm all configured cameras before starting experiments.")

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
        payload = self._load_camera_config_payload()
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
                    notes=str(record.get("notes") or ""),
                    last_confirmed_at=(
                        str(record["last_confirmed_at"])
                        if record.get("last_confirmed_at")
                        else None
                    ),
                    last_confirmed_index=(
                        int(record["last_confirmed_index"])
                        if record.get("last_confirmed_index") is not None
                        else None
                    ),
                )
            )
        return cameras

    def _load_camera_config_payload(self) -> dict[str, Any]:
        if not self.cameras_path.exists():
            raise CameraConfigError(
                f"Missing {self.cameras_path}; run tools/camera_setup.py setup first"
            )
        with self.cameras_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            raise CameraConfigError(f"Expected camera config object in {self.cameras_path}")
        return payload

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


def _capture_error_message(exc: Exception) -> str:
    message = str(exc).lower()
    if "not detected" in message or "unknown camera" in message or "could not open camera" in message:
        return "Camera is not detected. Check the USB connection."
    if "open camera" in message or "read frame" in message or "camera" in message:
        return "Camera is not responding. Check the USB connection."
    return "Capture failed. Check the camera and try again."


def _storage_error_message(exc: Exception) -> str:
    if _is_no_space_error(exc):
        return "Storage is full."
    return "Storage is not writable."


def _is_no_space_error(exc: Exception) -> bool:
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        return True
    text = str(exc).lower()
    return "no space left" in text or "not enough space" in text or "disk full" in text


def _is_storage_error(exc: Exception) -> bool:
    if isinstance(exc, (OSError, StorageError)):
        return True
    text = str(exc).lower()
    return "could not write jpeg" in text or "permission denied" in text or "not writable" in text
