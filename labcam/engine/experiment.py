from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from labcam.engine.storage import ExperimentPaths


ExperimentStatus = Literal["idle", "capturing", "finished", "stopped", "failed"]
EndReason = Literal["completed", "stopped_early", "unknown", "baseline_failed"]


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

    def advance_after_attempt(self) -> None:
        if self.next_capture_at is None:
            self.next_capture_at = self.started_at + self.interval
        else:
            self.next_capture_at = self.next_capture_at + self.interval
        self.sequence += 1

    def record_success(self) -> None:
        self.images_captured += 1

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
            "camera_label": self.config.camera_label,
            "next_capture_at": self.next_capture_at.astimezone().isoformat(timespec="seconds"),
            "planned_stop_at": self.planned_stop_at.astimezone().isoformat(timespec="seconds"),
            "images_captured": self.images_captured,
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
            "next_capture_at": (
                self.next_capture_at.astimezone().isoformat(timespec="seconds")
                if self.next_capture_at
                else None
            ),
            "latest_frame_path": str(latest) if latest else None,
            "folder": str(self.paths.root),
        }

    def latest_frame_path(self) -> Path | None:
        from labcam.engine.storage import latest_image_path

        return latest_image_path(self.paths)
