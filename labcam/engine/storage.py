from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from labcam.cameras.interface import save_jpeg


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
DEFAULT_JPEG_QUALITY = 90
POST_NOTES_FILENAME = "post_notes.txt"

_SAFE_NAME_PATTERN = re.compile(r"[^A-Za-z0-9-]+")


@dataclass(frozen=True)
class ExperimentPaths:
    root: Path
    images_dir: Path
    metadata_path: Path
    log_path: Path

    @property
    def experiment_id(self) -> str:
        return self.root.name


class StorageError(RuntimeError):
    """Raised when experiment files cannot be written."""


def local_now() -> datetime:
    return datetime.now().astimezone()


def sanitize_name(value: str) -> str:
    cleaned = _SAFE_NAME_PATTERN.sub("-", value.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    if not cleaned:
        raise StorageError("Experiment name must contain at least one letter or number")
    return cleaned


def iso_timestamp(value: datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds")


def filename_timestamp(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%dT%H-%M-%S")


def image_filename(sequence: int, captured_at: datetime) -> str:
    return f"{sequence:04d}_{filename_timestamp(captured_at)}.jpg"


def create_experiment_paths(
    *,
    experiments_dir: Path,
    experiment_name: str,
    camera_label: str,
    started_at: datetime,
) -> ExperimentPaths:
    safe_name = sanitize_name(experiment_name)
    safe_camera = sanitize_name(camera_label)
    date_prefix = started_at.astimezone().date().isoformat()
    base_name = f"{date_prefix}_{safe_name}_{safe_camera}"

    experiments_dir.mkdir(parents=True, exist_ok=True)
    folder = experiments_dir / base_name
    suffix = 2
    while folder.exists():
        folder = experiments_dir / f"{base_name}_{suffix}"
        suffix += 1

    images_dir = folder / "images"
    images_dir.mkdir(parents=True)
    return ExperimentPaths(
        root=folder,
        images_dir=images_dir,
        metadata_path=folder / "metadata.json",
        log_path=folder / "capture_log.txt",
    )


def build_metadata(
    *,
    name: str,
    camera_label: str,
    camera_id: str,
    camera_identity_strategy: str,
    interval_minutes: float,
    duration_hours: float,
    operator: str,
    notes: str,
    started_at: datetime,
    planned_stop_at: datetime,
    images_captured: int = 0,
    ended_at: datetime | None = None,
    end_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "name": sanitize_name(name),
        "camera_label": camera_label,
        "camera_id": camera_id,
        "camera_identity_strategy": camera_identity_strategy,
        "interval_minutes": interval_minutes,
        "duration_hours": duration_hours,
        "operator": operator,
        "notes": notes,
        "started_at": iso_timestamp(started_at),
        "planned_stop_at": iso_timestamp(planned_stop_at),
        "ended_at": iso_timestamp(ended_at) if ended_at else None,
        "end_reason": end_reason,
        "images_captured": images_captured,
        "interval_seconds_effective": int(round(interval_minutes * 60)),
    }


def write_metadata(paths: ExperimentPaths, metadata: dict[str, Any]) -> None:
    atomic_write_json(paths.metadata_path, metadata)


def update_metadata_finalize(
    metadata_path: Path,
    *,
    ended_at: datetime,
    end_reason: str,
    images_captured: int,
) -> dict[str, Any]:
    metadata = read_json_file(metadata_path)
    metadata["ended_at"] = iso_timestamp(ended_at)
    metadata["end_reason"] = end_reason
    metadata["images_captured"] = images_captured
    atomic_write_json(metadata_path, metadata)
    return metadata


def read_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise StorageError(f"Expected JSON object: {path}")
    return data


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def read_post_notes(experiment_root: Path) -> str:
    path = experiment_root / POST_NOTES_FILENAME
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_post_notes(experiment_root: Path, notes: str) -> bool:
    path = experiment_root / POST_NOTES_FILENAME
    cleaned = notes.strip()
    if not cleaned:
        try:
            path.unlink()
            _fsync_directory(experiment_root)
        except FileNotFoundError:
            pass
        return False

    atomic_write_text(path, notes)
    return True


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def append_log_line(log_path: Path, event_time: datetime, event: str, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{iso_timestamp(event_time)}  {event:<7} {message}\n")
        file.flush()
        os.fsync(file.fileno())


def save_frame_as_jpeg(
    *,
    image: Any,
    paths: ExperimentPaths,
    sequence: int,
    captured_at: datetime,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
    save_jpeg_func: Callable[..., Path] = save_jpeg,
) -> Path:
    output_path = paths.images_dir / image_filename(sequence, captured_at)
    return save_jpeg_func(image, output_path, quality=jpeg_quality)


def latest_image_path(paths: ExperimentPaths) -> Path | None:
    if not paths.images_dir.exists():
        return None
    images = sorted(paths.images_dir.glob("*.jpg"))
    return images[-1] if images else None


def _fsync_directory(path: Path) -> None:
    try:
        dir_fd = os.open(path, os.O_RDONLY)
    except OSError:
        return

    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)
