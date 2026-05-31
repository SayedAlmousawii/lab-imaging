from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from labcam.engine.storage import ExperimentPaths


ExperimentStatus = Literal["idle", "capturing", "maintenance", "finished", "stopped", "failed"]
EndReason = Literal[
    "completed",
    "stopped_early",
    "unknown",
    "baseline_failed",
    "disk_full",
    "storage_failed",
]
HealthState = Literal[
    "ok",
    "identity_warning",
    "capture_warning",
    "capture_failing",
    "camera_unavailable",
]


class EngineError(RuntimeError):
    """Base class for expected capture-engine failures."""


class CameraConfigError(EngineError):
    """Raised when a configured camera cannot be found or used."""


class ActiveExperimentError(EngineError):
    """Raised when a camera already has a running experiment."""


class DiskSpaceError(EngineError):
    """Raised when disk-space preflight fails."""


class BaselineCaptureError(EngineError):
    """Raised when the t=0 baseline capture cannot be completed."""


class ExperimentNotFoundError(EngineError):
    """Raised when an API caller references an unknown experiment."""


class ExperimentStateError(EngineError):
    """Raised when an experiment lifecycle transition is not allowed."""


@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    camera_label: str
    interval_minutes: float
    duration_hours: float
    operator: str = ""
    notes: str = ""

    def validate(self) -> None:
        if self.interval_minutes <= 0:
            raise EngineError("interval_minutes must be greater than 0")
        if self.duration_hours <= 0:
            raise EngineError("duration_hours must be greater than 0")
        if not self.camera_label.strip():
            raise CameraConfigError("camera_label is required")


@dataclass
class Experiment:
    config: ExperimentConfig
    camera_id: str
    camera_identity_strategy: str
    paths: ExperimentPaths
    started_at: datetime
    planned_stop_at: datetime
    sequence: int = 0
    images_captured: int = 0
    next_capture_at: datetime | None = None
    status: ExperimentStatus = "idle"
    ended_at: datetime | None = None
    end_reason: str | None = None
    stop_requested: bool = False
    consecutive_failures: int = 0
    last_error_message: str | None = None
    last_error_at: datetime | None = None
    terminal_health_message: str | None = None
    maintenance_started_at: datetime | None = None
    maintenance_note: str = ""
    maintenance_skipped_capture_count: int = 0
    maintenance_events: list[dict[str, object]] = field(default_factory=list)

    @property
    def experiment_id(self) -> str:
        return self.paths.experiment_id

    @property
    def interval(self) -> timedelta:
        return timedelta(minutes=self.config.interval_minutes)

    def start(self) -> None:
        self.status = "capturing"
        self.next_capture_at = self.started_at + self.interval

    def tick(self, now: datetime) -> bool:
        return (
            self.status == "capturing"
            and self.next_capture_at is not None
            and now >= self.next_capture_at
            and self.next_capture_at <= self.planned_stop_at
        )

    def enter_maintenance(self, *, started_at: datetime, note: str = "") -> dict[str, object]:
        if self.status != "capturing":
            raise ExperimentStateError("Only running experiments can enter maintenance.")
        self.status = "maintenance"
        self.maintenance_started_at = started_at
        self.maintenance_note = note.strip()
        self.maintenance_skipped_capture_count = 0
        event: dict[str, object] = {
            "started_at": started_at.astimezone().isoformat(timespec="seconds"),
            "ended_at": None,
            "note": self.maintenance_note,
            "skipped_capture_count": 0,
        }
        self.maintenance_events.append(event)
        return event

    def record_maintenance_skips_until(self, until: datetime) -> int:
        if self.status != "maintenance" or self.next_capture_at is None:
            return 0

        skipped = 0
        limit = min(until, self.planned_stop_at)
        while self.next_capture_at <= limit:
            self.maintenance_skipped_capture_count += 1
            skipped += 1
            self.next_capture_at = self.next_capture_at + self.interval

        if skipped and self.maintenance_events:
            self.maintenance_events[-1]["skipped_capture_count"] = (
                self.maintenance_skipped_capture_count
            )
        return skipped

    def resume_from_maintenance(self, *, resumed_at: datetime) -> dict[str, object]:
        if self.status != "maintenance":
            raise ExperimentStateError("Only experiments in maintenance can resume.")
        self.record_maintenance_skips_until(resumed_at)
        self.status = "capturing"
        self.maintenance_started_at = None
        self.maintenance_note = ""
        if self.maintenance_events:
            self.maintenance_events[-1]["ended_at"] = (
                resumed_at.astimezone().isoformat(timespec="seconds")
            )
            self.maintenance_events[-1]["skipped_capture_count"] = (
                self.maintenance_skipped_capture_count
            )
            return self.maintenance_events[-1]
        return {}

    def close_maintenance(self, *, ended_at: datetime) -> dict[str, object] | None:
        if self.status != "maintenance":
            return None
        self.record_maintenance_skips_until(ended_at)
        self.maintenance_started_at = None
        self.maintenance_note = ""
        if self.maintenance_events:
            self.maintenance_events[-1]["ended_at"] = (
                ended_at.astimezone().isoformat(timespec="seconds")
            )
            self.maintenance_events[-1]["skipped_capture_count"] = (
                self.maintenance_skipped_capture_count
            )
            return self.maintenance_events[-1]
        return None

    def advance_after_attempt(self) -> None:
        if self.next_capture_at is None:
            self.next_capture_at = self.started_at + self.interval
        else:
            self.next_capture_at = self.next_capture_at + self.interval
        self.sequence += 1

    def record_success(self) -> None:
        self.images_captured += 1
        self.clear_capture_health()

    def record_capture_failure(self, *, message: str, failed_at: datetime) -> None:
        self.consecutive_failures += 1
        self.last_error_message = message
        self.last_error_at = failed_at

    def clear_capture_health(self) -> None:
        self.consecutive_failures = 0
        self.last_error_message = None
        self.last_error_at = None

    def mark_terminal_health(self, *, message: str, failed_at: datetime) -> None:
        self.terminal_health_message = message
        self.last_error_message = message
        self.last_error_at = failed_at

    def finalize(self, reason: EndReason | str, ended_at: datetime) -> None:
        self.ended_at = ended_at
        self.end_reason = reason
        if reason == "completed":
            self.status = "finished"
        elif reason == "stopped_early":
            self.status = "stopped"
        else:
            self.status = "failed"

    def to_running_state(self) -> dict[str, object]:
        if self.next_capture_at is None:
            raise EngineError(f"Experiment is missing next_capture_at: {self.experiment_id}")
        return {
            "experiment_id": self.experiment_id,
            "experiment_folder": str(self.paths.root),
            "camera_label": self.config.camera_label,
            "next_capture_at": self.next_capture_at.astimezone().isoformat(timespec="seconds"),
            "planned_stop_at": self.planned_stop_at.astimezone().isoformat(timespec="seconds"),
            "images_captured": self.images_captured,
            "status": self.status,
            "maintenance_started_at": (
                self.maintenance_started_at.astimezone().isoformat(timespec="seconds")
                if self.maintenance_started_at
                else None
            ),
            "maintenance_note": self.maintenance_note,
            "maintenance_skipped_capture_count": self.maintenance_skipped_capture_count,
        }

    def to_status(self) -> dict[str, object]:
        latest = self.latest_frame_path()
        return {
            "experiment_id": self.experiment_id,
            "name": self.config.name,
            "camera_label": self.config.camera_label,
            "status": self.status,
            "started_at": self.started_at.astimezone().isoformat(timespec="seconds"),
            "planned_stop_at": self.planned_stop_at.astimezone().isoformat(timespec="seconds"),
            "ended_at": self.ended_at.astimezone().isoformat(timespec="seconds") if self.ended_at else None,
            "end_reason": self.end_reason,
            "images_captured": self.images_captured,
            "interval_minutes": self.config.interval_minutes,
            "next_capture_at": (
                self.next_capture_at.astimezone().isoformat(timespec="seconds")
                if self.next_capture_at
                else None
            ),
            "health_state": self.health_state(),
            "health_message": self.health_message(),
            "consecutive_failures": self.consecutive_failures,
            "last_error_at": (
                self.last_error_at.astimezone().isoformat(timespec="seconds")
                if self.last_error_at
                else None
            ),
            "maintenance_started_at": (
                self.maintenance_started_at.astimezone().isoformat(timespec="seconds")
                if self.maintenance_started_at
                else None
            ),
            "maintenance_note": self.maintenance_note,
            "maintenance_skipped_capture_count": self.maintenance_skipped_capture_count,
            "maintenance_events": self.maintenance_events,
            "latest_frame_path": str(latest) if latest else None,
            "folder": str(self.paths.root),
        }

    def health_state(self) -> HealthState:
        if self.last_error_message and "not detected" in self.last_error_message.lower():
            return "camera_unavailable"
        if self.end_reason in {"disk_full", "storage_failed"}:
            return "capture_failing"
        if self.consecutive_failures >= 3:
            return "capture_failing"
        if self.consecutive_failures > 0:
            return "capture_warning"
        if self.camera_identity_strategy != "hardware_id":
            return "identity_warning"
        return "ok"

    def health_message(self) -> str | None:
        if self.terminal_health_message:
            return self.terminal_health_message
        if self.consecutive_failures > 0:
            return self.last_error_message or "Camera is not responding. Check the USB connection."
        if self.camera_identity_strategy != "hardware_id":
            return "Camera identity may change if cameras are replugged. Verify preview before long runs."
        return None

    def latest_frame_path(self) -> Path | None:
        from labcam.engine.storage import latest_image_path

        return latest_image_path(self.paths)
