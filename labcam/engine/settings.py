from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from labcam.engine.storage import atomic_write_json


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_EXAMPLE_PATH = PROJECT_ROOT / "config" / "settings.json.example"

CAPTURE_DEFAULT_SETTINGS = (
    "default_interval_minutes",
    "default_duration_hours",
    "jpeg_quality",
    "capture_retries",
    "warmup_frames",
)
STORAGE_SETTINGS = ("experiments_dir",)
EDITABLE_SETTINGS = {*STORAGE_SETTINGS, *CAPTURE_DEFAULT_SETTINGS}
EDITABLE_SETTINGS_ORDER = (*STORAGE_SETTINGS, *CAPTURE_DEFAULT_SETTINGS)


class SettingsError(RuntimeError):
    """Raised when settings cannot be loaded, validated, or saved."""


def ensure_settings_file(
    settings_path: Path,
    *,
    example_path: Path = DEFAULT_SETTINGS_EXAMPLE_PATH,
) -> dict[str, Any]:
    if settings_path.exists():
        return read_settings_file(settings_path)

    defaults = read_settings_file(example_path)
    atomic_write_json(settings_path, defaults)
    return defaults


def load_effective_settings(
    settings_path: Path,
    *,
    example_path: Path = DEFAULT_SETTINGS_EXAMPLE_PATH,
    create_missing: bool = False,
) -> dict[str, Any]:
    defaults = read_settings_file(example_path)
    current = ensure_settings_file(settings_path, example_path=example_path) if create_missing else (
        read_settings_file(settings_path) if settings_path.exists() else {}
    )
    return {**defaults, **current}


def save_editable_settings(
    settings_path: Path,
    payload: dict[str, Any],
    *,
    example_path: Path = DEFAULT_SETTINGS_EXAMPLE_PATH,
    project_root: Path = PROJECT_ROOT,
    allow_capture_defaults: bool = True,
) -> dict[str, Any]:
    current = ensure_settings_file(settings_path, example_path=example_path)
    defaults = read_settings_file(example_path)
    effective = {**defaults, **current}
    updates, errors = validate_editable_settings(
        payload,
        current_settings=effective,
        project_root=project_root,
        allow_capture_defaults=allow_capture_defaults,
    )
    if errors:
        raise SettingsError(json.dumps(errors, sort_keys=True))

    next_settings = {**defaults, **current, **updates}
    atomic_write_json(settings_path, next_settings)
    return next_settings


def validate_editable_settings(
    payload: dict[str, Any],
    *,
    current_settings: dict[str, Any] | None = None,
    project_root: Path = PROJECT_ROOT,
    allow_capture_defaults: bool = True,
) -> tuple[dict[str, Any], dict[str, str]]:
    current_settings = current_settings or {}
    effective_payload = {**current_settings, **payload}
    updates: dict[str, Any] = {}
    errors: dict[str, str] = {}
    locked_message = "Stop running experiments before changing capture defaults."

    experiments_dir = str(effective_payload.get("experiments_dir") or "").strip()
    if not experiments_dir:
        errors["experiments_dir"] = "Experiment folder is required."
    elif _validate_experiments_dir(experiments_dir, project_root=project_root, errors=errors):
        updates["experiments_dir"] = experiments_dir

    updates["default_interval_minutes"] = _positive_float(
        effective_payload,
        "default_interval_minutes",
        "Default interval must be greater than 0.",
        errors,
    )
    updates["default_duration_hours"] = _positive_float(
        effective_payload,
        "default_duration_hours",
        "Default duration must be greater than 0.",
        errors,
    )
    updates["jpeg_quality"] = _bounded_int(
        effective_payload,
        "jpeg_quality",
        minimum=1,
        maximum=100,
        message="JPEG quality must be an integer from 1 to 100.",
        errors=errors,
    )
    updates["capture_retries"] = _non_negative_int(
        effective_payload,
        "capture_retries",
        "Capture retries must be a non-negative integer.",
        errors,
    )
    updates["warmup_frames"] = _non_negative_int(
        effective_payload,
        "warmup_frames",
        "Warmup frames must be a non-negative integer.",
        errors,
    )

    if not allow_capture_defaults:
        for key in CAPTURE_DEFAULT_SETTINGS:
            if key in errors:
                continue
            if updates.get(key) != current_settings.get(key):
                errors[key] = locked_message

    return ({key: value for key, value in updates.items() if key not in errors}, errors)


def read_settings_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except FileNotFoundError as exc:
        raise SettingsError(f"Missing settings file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SettingsError(f"Settings file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SettingsError(f"Expected settings object in {path}")
    return payload


def resolve_experiments_dir(value: Any, *, project_root: Path = PROJECT_ROOT) -> Path:
    path = Path(str(value or "./experiments").strip()).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _validate_experiments_dir(
    value: str,
    *,
    project_root: Path,
    errors: dict[str, str],
) -> bool:
    directory = resolve_experiments_dir(value, project_root=project_root)
    if directory.exists() and not directory.is_dir():
        errors["experiments_dir"] = "Experiment folder must be a directory, not a file."
        return False

    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors["experiments_dir"] = f"Could not create experiment folder: {exc}"
        return False

    test_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".labcam-write-test-",
            dir=directory,
            delete=False,
        ) as test_file:
            test_path = Path(test_file.name)
            test_file.write(b"ok")
            test_file.flush()
            os.fsync(test_file.fileno())
    except OSError as exc:
        errors["experiments_dir"] = f"Experiment folder is not writable: {exc}"
        return False
    finally:
        if test_path is not None:
            try:
                test_path.unlink(missing_ok=True)
            except OSError:
                pass

    return True


def _positive_float(
    payload: dict[str, Any],
    key: str,
    message: str,
    errors: dict[str, str],
) -> float:
    try:
        value = float(payload.get(key))
    except (TypeError, ValueError):
        errors[key] = message
        return 0
    if value <= 0:
        errors[key] = message
    return value


def _non_negative_int(
    payload: dict[str, Any],
    key: str,
    message: str,
    errors: dict[str, str],
) -> int:
    try:
        value = int(payload.get(key))
    except (TypeError, ValueError):
        errors[key] = message
        return 0
    if str(payload.get(key)).strip() not in {str(value), f"{value}.0"}:
        errors[key] = message
    if value < 0:
        errors[key] = message
    return value


def _bounded_int(
    payload: dict[str, Any],
    key: str,
    *,
    minimum: int,
    maximum: int,
    message: str,
    errors: dict[str, str],
) -> int:
    value = _non_negative_int(payload, key, message, errors)
    if key not in errors and not minimum <= value <= maximum:
        errors[key] = message
    return value
