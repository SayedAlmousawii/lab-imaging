from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, url_for

from labcam.cameras.interface import get_opencv_version
from labcam.engine import (
    ActiveExperimentError,
    BaselineCaptureError,
    CameraConfigError,
    CaptureEngine,
    DiskSpaceError,
    EngineError,
    ExperimentConfig,
    ExperimentNotFoundError,
)
from labcam.engine.scheduler import PROJECT_ROOT
from labcam.engine.settings import (
    CAPTURE_DEFAULT_SETTINGS,
    EDITABLE_SETTINGS_ORDER,
    SettingsError,
    load_effective_settings,
    save_editable_settings,
)
from labcam.engine.storage import (
    POST_NOTES_FILENAME,
    StorageError,
    read_json_file,
    read_post_notes,
    sanitize_name,
    write_post_notes,
)


EXPERIMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def create_app(engine: CaptureEngine) -> Flask:
    app = Flask(__name__)
    app.config["LABCAM_ENGINE"] = engine

    @app.get("/")
    def status_page() -> Response | str:
        if not engine.cameras_path.exists():
            return redirect(url_for("cameras_page"))
        if engine.verification_required():
            return redirect(url_for("verify_cameras_page"))
        return render_template("status.html")

    @app.get("/new")
    def new_experiment_page() -> Response | str:
        if not engine.cameras_path.exists():
            return redirect(url_for("cameras_page"))
        if engine.verification_required():
            return redirect(url_for("verify_cameras_page"))
        return render_template(
            "new.html",
            default_interval_minutes=engine.settings.get("default_interval_minutes", 5),
            default_duration_hours=engine.settings.get("default_duration_hours", 12),
        )

    @app.get("/cameras")
    def cameras_page() -> str:
        return render_template("cameras.html")

    @app.get("/settings")
    def settings_page() -> str:
        return render_template("settings.html")

    @app.get("/experiments")
    def experiments_page() -> str:
        return render_template("experiments.html")

    @app.get("/experiments/<experiment_id>")
    def experiment_detail_page(experiment_id: str) -> str:
        return render_template("experiment_detail.html", experiment_id=experiment_id)

    @app.get("/verify-cameras")
    def verify_cameras_page() -> str:
        return render_template("verify.html")

    @app.get("/experiments/<experiment_id>/notes")
    def experiment_notes_page(experiment_id: str) -> str:
        return render_template("experiment_notes.html", experiment_id=experiment_id)

    @app.get("/api/cameras")
    def api_cameras() -> Response:
        try:
            cameras = [
                {
                    "label": camera.label,
                    "identity_strategy": camera.identity_strategy,
                    "stable_id": camera.stable_id,
                    "warnings": camera.warnings,
                }
                for camera in engine.list_cameras()
            ]
        except CameraConfigError as exc:
            return _error("missing_camera_config", str(exc), 500)
        return jsonify({"cameras": cameras})

    @app.get("/api/cameras/detected")
    def api_detected_cameras() -> Response:
        try:
            return jsonify({
                "configured": _configured_camera_payload(engine),
                "detected": engine.detected_cameras(),
            })
        except ActiveExperimentError as exc:
            return _error("camera_setup_busy", str(exc), 409)
        except Exception as exc:
            return _error("camera_detection_failed", _capture_message(exc), 500)

    @app.post("/api/cameras/detected/preview")
    def api_detected_camera_preview() -> Response:
        payload = _json_payload()
        try:
            camera_index = int(payload.get("camera_index"))
            preview_path = engine.preview_detected_camera(camera_index)
        except (TypeError, ValueError):
            return _error("missing_camera", "camera_index is required", 400)
        except ActiveExperimentError as exc:
            return _error("camera_busy", str(exc), 409)
        except CameraConfigError as exc:
            return _error("unknown_camera", _camera_config_message(exc), 400)
        except Exception as exc:
            return _error("preview_failed", _capture_message(exc), 500)
        return send_file(preview_path, mimetype="image/jpeg", max_age=0)

    @app.post("/api/cameras/config")
    def api_save_camera_config() -> Response:
        payload = _json_payload()
        mappings = payload.get("mappings")
        if not isinstance(mappings, list):
            return _error("invalid_mapping", "mappings must be a list", 400)
        try:
            verification = engine.save_camera_config(mappings)
        except CameraConfigError as exc:
            return _error("invalid_mapping", str(exc), 400)
        return jsonify({
            "configured": _configured_camera_payload(engine),
            "verification": verification,
        })

    @app.post("/api/cameras/stress-test")
    def api_camera_stress_test() -> Response:
        payload = _json_payload()
        indexes = payload.get("camera_indexes")
        if not isinstance(indexes, list):
            return _error("invalid_stress_test", "camera_indexes must be a list", 400)
        try:
            cycles = int(payload.get("cycles") or 100)
            results = engine.stress_test_cameras([int(index) for index in indexes], cycles=cycles)
        except (TypeError, ValueError):
            return _error("invalid_stress_test", "camera indexes and cycles must be numbers", 400)
        except ActiveExperimentError as exc:
            return _error("camera_busy", str(exc), 409)
        except CameraConfigError as exc:
            return _error("invalid_stress_test", str(exc), 400)
        return jsonify(results)

    @app.post("/api/preview")
    def api_preview() -> Response:
        payload = _json_payload()
        camera_label = str(payload.get("camera_label") or "").strip()
        if not camera_label:
            return _error("missing_camera", "camera_label is required", 400)

        try:
            preview_path = engine.preview(camera_label)
        except ActiveExperimentError as exc:
            return _error("camera_busy", str(exc), 409)
        except CameraConfigError as exc:
            return _error("unknown_camera", _camera_config_message(exc), 400)
        except Exception as exc:
            return _error("preview_failed", _capture_message(exc), 500)

        return send_file(preview_path, mimetype="image/jpeg", max_age=0)

    @app.get("/api/verification")
    def api_verification() -> Response:
        try:
            status = engine.verification_status()
        except CameraConfigError as exc:
            return _error("missing_camera_config", str(exc), 500)
        return jsonify(status)

    @app.post("/api/verification/confirm")
    def api_verification_confirm() -> Response:
        payload = _json_payload()
        camera_label = str(payload.get("camera_label") or "").strip()
        if not camera_label:
            return _error("missing_camera", "camera_label is required", 400)

        try:
            status = engine.confirm_camera(camera_label)
        except ActiveExperimentError as exc:
            return _error("camera_busy", str(exc), 409)
        except CameraConfigError as exc:
            return _error("unknown_camera", _camera_config_message(exc), 400)
        except Exception as exc:
            return _error("preview_failed", _capture_message(exc), 500)
        return jsonify(status)

    @app.post("/api/experiments")
    def api_start_experiment() -> Response:
        payload = _json_payload()
        try:
            config = _experiment_config_from_payload(payload)
            experiment_id = engine.start_experiment(config)
        except StorageError as exc:
            return _error("invalid_name", str(exc), 400)
        except ValueError as exc:
            return _error("invalid_number", str(exc), 400)
        except ActiveExperimentError as exc:
            return _error("camera_busy", str(exc), 409)
        except BaselineCaptureError as exc:
            return _error("baseline_failed", str(exc), 500)
        except DiskSpaceError as exc:
            return _error("disk_full", _disk_space_message(exc), 507)
        except CameraConfigError as exc:
            return _error("unknown_camera", _camera_config_message(exc), 400)
        except EngineError as exc:
            return _error("invalid_request", str(exc), 400)

        return jsonify({"experiment_id": experiment_id})

    @app.post("/api/experiments/name-check")
    def api_experiment_name_check() -> Response:
        payload = _json_payload()
        camera_label = str(payload.get("camera_label") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not camera_label or not name:
            return jsonify({"duplicate": False})

        try:
            preview = _experiment_folder_preview(engine, name=name, camera_label=camera_label)
        except StorageError as exc:
            return _error("invalid_name", str(exc), 400)
        except CameraConfigError as exc:
            return _error("unknown_camera", _camera_config_message(exc), 400)
        return jsonify(preview)

    @app.get("/api/experiments")
    def api_experiment_browser() -> Response:
        return jsonify(_experiment_browser_payload(
            engine,
            date_filter=str(request.args.get("date") or "").strip(),
            station_filter=str(request.args.get("station") or "").strip(),
        ))

    @app.get("/api/experiments/<experiment_id>")
    def api_experiment_detail(experiment_id: str) -> Response:
        try:
            folder = _experiment_folder(engine, experiment_id)
            record = _experiment_record(
                engine,
                folder,
                runtime=_runtime_experiments_by_id(engine).get(experiment_id),
                include_detail=True,
            )
        except ValueError as exc:
            return _error("invalid_experiment_id", str(exc), 400)
        except ExperimentNotFoundError as exc:
            return _error("not_found", str(exc), 404)
        return jsonify({"experiment": record})

    @app.post("/api/experiments/<experiment_id>/stop")
    def api_stop_experiment(experiment_id: str) -> Response:
        try:
            engine.stop_experiment(experiment_id)
        except ExperimentNotFoundError as exc:
            return _error("not_found", str(exc), 404)

        status = _wait_for_final_status(engine, experiment_id)
        if status is None:
            return jsonify({"experiment_id": experiment_id, "status": "stopping"})
        return jsonify(status)

    @app.get("/api/status")
    def api_status() -> Response:
        return jsonify({
            "stations": _station_status(engine),
            "verification": engine.verification_status(),
        })

    @app.get("/api/experiments/<experiment_id>/latest")
    def api_latest(experiment_id: str) -> Response:
        try:
            latest = engine.latest_frame_path(experiment_id)
        except ExperimentNotFoundError as exc:
            try:
                latest = _latest_experiment_image(_experiment_folder(engine, experiment_id))
            except ValueError as folder_exc:
                return _error("invalid_experiment_id", str(folder_exc), 400)
            except ExperimentNotFoundError:
                return _error("not_found", str(exc), 404)
        if latest is None or not latest.exists():
            return _error("no_frame", "No captured frame is available yet", 404)
        return send_file(latest, mimetype="image/jpeg", max_age=0)

    @app.get("/api/experiments/<experiment_id>/post-notes")
    def api_get_post_notes(experiment_id: str) -> Response:
        try:
            return jsonify(_post_notes_payload(engine, experiment_id))
        except ValueError as exc:
            return _error("invalid_experiment_id", str(exc), 400)
        except ActiveExperimentError as exc:
            return _error("experiment_active", str(exc), 409)
        except ExperimentNotFoundError as exc:
            return _error("not_found", str(exc), 404)
        except StorageError as exc:
            return _error("metadata_unavailable", str(exc), 422)

    @app.post("/api/experiments/<experiment_id>/post-notes")
    def api_save_post_notes(experiment_id: str) -> Response:
        payload = _json_payload()
        notes = str(payload.get("notes") or "")
        try:
            context = _post_notes_context(engine, experiment_id)
            write_post_notes(context["folder"], notes)
            return jsonify(_post_notes_payload(engine, experiment_id))
        except ValueError as exc:
            return _error("invalid_experiment_id", str(exc), 400)
        except ActiveExperimentError as exc:
            return _error("experiment_active", str(exc), 409)
        except ExperimentNotFoundError as exc:
            return _error("not_found", str(exc), 404)
        except StorageError as exc:
            return _error("metadata_unavailable", str(exc), 422)
        except OSError as exc:
            return _error("notes_not_saved", f"Could not save post-run notes: {exc}", 500)

    @app.get("/api/settings")
    def api_settings() -> Response:
        try:
            settings = load_effective_settings(engine.settings_path, create_missing=True)
            engine.reload_settings()
        except SettingsError as exc:
            return _error("settings_unavailable", str(exc), 500)
        return jsonify(_settings_payload(engine, settings))

    @app.post("/api/settings")
    def api_save_settings() -> Response:
        active_experiments = engine.has_active_experiments()
        payload = _json_payload()
        try:
            settings = save_editable_settings(
                engine.settings_path,
                payload,
                allow_capture_defaults=not active_experiments,
            )
        except SettingsError as exc:
            fields = _settings_error_fields(exc)
            if active_experiments and any(field in CAPTURE_DEFAULT_SETTINGS for field in fields):
                return _error(
                    "settings_busy",
                    "Stop running experiments before changing capture defaults.",
                    409,
                    fields=fields,
                )
            return _error(
                "invalid_settings",
                "Check the highlighted settings and try again.",
                400,
                fields=fields,
            )
        engine.reload_settings()
        return jsonify(_settings_payload(engine, settings))

    return app


def _json_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _experiment_config_from_payload(payload: dict[str, Any]) -> ExperimentConfig:
    name = str(payload.get("name") or "").strip()
    sanitize_name(name)
    interval_minutes = float(payload.get("interval_minutes"))
    duration_hours = float(payload.get("duration_hours"))
    return ExperimentConfig(
        name=name,
        camera_label=str(payload.get("camera_label") or "").strip(),
        interval_minutes=interval_minutes,
        duration_hours=duration_hours,
        operator=str(payload.get("operator") or "").strip(),
        notes=str(payload.get("notes") or "").strip(),
    )


def _experiment_folder_preview(
    engine: CaptureEngine,
    *,
    name: str,
    camera_label: str,
) -> dict[str, Any]:
    camera_labels = {camera.label for camera in engine.list_cameras()}
    if camera_label not in camera_labels:
        raise CameraConfigError(f"Unknown camera label {camera_label!r}")

    safe_name = sanitize_name(name)
    safe_camera = sanitize_name(camera_label)
    date_prefix = datetime.now().astimezone().date().isoformat()
    base_name = f"{date_prefix}_{safe_name}_{safe_camera}"
    base_folder = engine.experiments_dir / base_name
    folder = base_folder
    suffix = 2
    while folder.exists():
        folder = engine.experiments_dir / f"{base_name}_{suffix}"
        suffix += 1

    return {
        "duplicate": base_folder.exists(),
        "base_folder_name": base_name,
        "next_folder_name": folder.name,
    }


def _configured_camera_payload(engine: CaptureEngine) -> list[dict[str, Any]]:
    if not engine.cameras_path.exists():
        return []
    return [
        {
            "label": camera.label,
            "identity_strategy": camera.identity_strategy,
            "stable_id": camera.stable_id,
            "last_seen_index": camera.last_seen_index,
            "warnings": camera.warnings,
            "notes": camera.notes,
            "last_confirmed_at": camera.last_confirmed_at,
            "last_confirmed_index": camera.last_confirmed_index,
        }
        for camera in engine.list_cameras()
    ]


def _experiment_browser_payload(
    engine: CaptureEngine,
    *,
    date_filter: str = "",
    station_filter: str = "",
) -> dict[str, Any]:
    root = engine.experiments_dir.resolve()
    runtime_by_id = _runtime_experiments_by_id(engine)
    records = [
        _experiment_record(engine, folder, runtime=runtime_by_id.get(folder.name))
        for folder in _experiment_folders(root)
    ]
    records.sort(key=_experiment_sort_key, reverse=True)

    dates = sorted({record["date"] for record in records if record.get("date")}, reverse=True)
    stations = sorted({record["camera_label"] for record in records if record.get("camera_label")})

    filtered = records
    if date_filter:
        filtered = [record for record in filtered if record.get("date") == date_filter]
    if station_filter:
        filtered = [record for record in filtered if record.get("camera_label") == station_filter]

    return {
        "experiments_dir": str(root),
        "filters": {"date": date_filter, "station": station_filter},
        "dates": dates,
        "stations": stations,
        "experiments": filtered,
        "total_count": len(records),
        "filtered_count": len(filtered),
    }


def _experiment_folders(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    return [
        child
        for child in root.iterdir()
        if child.is_dir() and EXPERIMENT_ID_PATTERN.fullmatch(child.name)
    ]


def _runtime_experiments_by_id(engine: CaptureEngine) -> dict[str, dict[str, Any]]:
    return {
        str(experiment.get("experiment_id")): experiment
        for experiment in engine.list_experiments()
        if experiment.get("experiment_id")
    }


def _experiment_record(
    engine: CaptureEngine,
    folder: Path,
    *,
    runtime: dict[str, Any] | None = None,
    include_detail: bool = False,
) -> dict[str, Any]:
    parsed = _parse_experiment_folder_name(folder.name)
    metadata_path = folder / "metadata.json"
    metadata: dict[str, Any] = {}
    warnings: list[str] = []
    metadata_status = "missing"

    if metadata_path.exists():
        try:
            metadata = read_json_file(metadata_path)
        except (json.JSONDecodeError, OSError, StorageError):
            warnings.append("metadata.json could not be read. This folder may be incomplete.")
            metadata_status = "malformed"
        else:
            metadata_status = "ok"
    else:
        warnings.append("metadata.json is missing. This folder may be incomplete.")

    name = str(metadata.get("name") or parsed["name"] or folder.name)
    camera_label = str(metadata.get("camera_label") or parsed["camera_label"] or "")
    started_at = _metadata_or_runtime(metadata, runtime, "started_at")
    planned_stop_at = _metadata_or_runtime(metadata, runtime, "planned_stop_at")
    ended_at = _metadata_or_runtime(metadata, runtime, "ended_at")
    end_reason = _metadata_or_runtime(metadata, runtime, "end_reason")
    images = _experiment_images(folder)
    image_count = _int_or_count(metadata.get("images_captured"), len(images))

    if runtime:
        image_count = int(runtime.get("images_captured") or image_count)
        if runtime.get("status") == "capturing":
            end_reason = ""

    date_value = _date_from_timestamp(started_at) or parsed["date"]
    status = _experiment_status_label(
        metadata_status=metadata_status,
        runtime_status=str(runtime.get("status") if runtime else ""),
        ended_at=ended_at,
        end_reason=end_reason,
    )
    latest = images[-1] if images else None
    has_post_notes = (folder / POST_NOTES_FILENAME).exists()
    is_terminal = bool(ended_at and end_reason and status != "incomplete")

    record: dict[str, Any] = {
        "experiment_id": folder.name,
        "name": name,
        "date": date_value,
        "camera_label": camera_label,
        "status": status,
        "end_reason": end_reason or None,
        "images_captured": image_count,
        "folder": str(folder),
        "metadata_status": metadata_status,
        "warnings": warnings,
        "started_at": started_at or None,
        "planned_stop_at": planned_stop_at or None,
        "ended_at": ended_at or None,
        "latest_image_url": f"/api/experiments/{folder.name}/latest" if latest else None,
        "detail_url": f"/experiments/{folder.name}",
        "post_notes_url": f"/experiments/{folder.name}/notes" if is_terminal else None,
        "has_post_notes": has_post_notes,
    }

    if include_detail:
        record["metadata"] = metadata
        record["capture_log"] = _capture_log_summary(folder / "capture_log.txt")
        record["post_notes"] = read_post_notes(folder) if has_post_notes else ""
        record["latest_image"] = latest.name if latest else None
    return record


def _metadata_or_runtime(
    metadata: dict[str, Any],
    runtime: dict[str, Any] | None,
    key: str,
) -> str:
    value = metadata.get(key)
    if (value is None or value == "") and runtime:
        value = runtime.get(key)
    return str(value or "")


def _parse_experiment_folder_name(folder_name: str) -> dict[str, str]:
    parts = folder_name.split("_")
    date_value = parts[0] if parts and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]) else ""
    if len(parts) < 3:
        return {"date": date_value, "name": "", "camera_label": ""}

    body = parts[1:]
    if len(body) >= 3 and body[-1].isdigit():
        body = body[:-1]
    camera_label = body[-1] if body else ""
    name = "_".join(body[:-1])
    return {"date": date_value, "name": name, "camera_label": camera_label}


def _experiment_images(folder: Path) -> list[Path]:
    images_dir = folder / "images"
    if not images_dir.exists() or not images_dir.is_dir():
        return []
    return sorted(path for path in images_dir.glob("*.jpg") if path.is_file())


def _latest_experiment_image(folder: Path) -> Path | None:
    images = _experiment_images(folder)
    return images[-1] if images else None


def _int_or_count(value: Any, fallback: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return fallback
    return result if result >= 0 else fallback


def _date_from_timestamp(value: str) -> str:
    if re.match(r"^\d{4}-\d{2}-\d{2}", value or ""):
        return value[:10]
    return ""


def _experiment_status_label(
    *,
    metadata_status: str,
    runtime_status: str,
    ended_at: str,
    end_reason: str,
) -> str:
    if metadata_status != "ok":
        return "incomplete"
    if runtime_status == "capturing":
        return "running"
    if not ended_at or not end_reason:
        return "incomplete"
    if end_reason in {"baseline_failed", "disk_full", "storage_failed", "unknown"}:
        return "failed"
    if end_reason == "stopped_early":
        return "stopped"
    return "completed"


def _capture_log_summary(log_path: Path) -> dict[str, Any]:
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {
            "available": False,
            "line_count": 0,
            "error_count": 0,
            "recent_lines": [],
            "warning": "capture_log.txt is missing.",
        }
    except OSError as exc:
        return {
            "available": False,
            "line_count": 0,
            "error_count": 0,
            "recent_lines": [],
            "warning": f"capture_log.txt could not be read: {exc}",
        }
    return {
        "available": True,
        "line_count": len(lines),
        "error_count": sum(1 for line in lines if " ERROR " in line),
        "recent_lines": lines[-8:],
        "warning": None,
    }


def _experiment_sort_key(record: dict[str, Any]) -> tuple[str, str]:
    return (
        str(record.get("started_at") or record.get("date") or ""),
        str(record.get("experiment_id") or ""),
    )


def _station_status(engine: CaptureEngine) -> list[dict[str, Any]]:
    now = datetime.now().astimezone()
    experiments = engine.list_experiments()
    by_camera: dict[str, dict[str, Any]] = {}
    for experiment in experiments:
        camera_label = str(experiment.get("camera_label"))
        if experiment.get("status") == "capturing":
            by_camera[camera_label] = experiment
            continue
        current = by_camera.get(camera_label)
        if current is None or (
            current.get("status") != "capturing"
            and _sort_time(experiment) >= _sort_time(current)
        ):
            by_camera[camera_label] = experiment

    stations: list[dict[str, Any]] = []
    for camera in engine.list_cameras():
        experiment = by_camera.get(camera.label)
        if experiment is None:
            unavailable_message = engine.camera_unavailable_message(camera)
            health_state = (
                "camera_unavailable"
                if unavailable_message
                else _idle_health_state(camera.identity_strategy)
            )
            stations.append(
                {
                    "camera_label": camera.label,
                    "state": "offline" if unavailable_message else "idle",
                    "identity_strategy": camera.identity_strategy,
                    "warnings": camera.warnings,
                    "health_state": health_state,
                    "health_message": unavailable_message
                    or _identity_health_message(camera.identity_strategy),
                    "consecutive_failures": 0,
                    "last_error_at": None,
                }
            )
            continue

        health_state = str(experiment.get("health_state") or _idle_health_state(camera.identity_strategy))
        state = _station_state_for_health(experiment, health_state)
        started_at = _parse_iso(str(experiment.get("started_at")))
        planned_stop_at = _parse_iso(str(experiment.get("planned_stop_at")))
        ended_at = (
            _parse_iso(str(experiment.get("ended_at")))
            if experiment.get("ended_at")
            else None
        )
        next_capture_at = (
            _parse_iso(str(experiment.get("next_capture_at")))
            if experiment.get("next_capture_at")
            else None
        )
        latest_url = None
        if experiment.get("latest_frame_path"):
            latest_url = f"/api/experiments/{experiment['experiment_id']}/latest"
        is_terminal = experiment.get("status") != "capturing"
        notes_url = (
            f"/experiments/{experiment['experiment_id']}/notes"
            if is_terminal and experiment.get("experiment_id")
            else None
        )
        has_post_notes = False
        folder = experiment.get("folder")
        if is_terminal and folder:
            has_post_notes = (Path(str(folder)) / POST_NOTES_FILENAME).exists()
        stations.append(
            {
                "camera_label": camera.label,
                "state": state,
                "identity_strategy": camera.identity_strategy,
                "warnings": camera.warnings,
                "health_state": health_state,
                "health_message": experiment.get("health_message"),
                "consecutive_failures": experiment.get("consecutive_failures"),
                "last_error_at": experiment.get("last_error_at"),
                "error_message": experiment.get("health_message"),
                "experiment_id": experiment.get("experiment_id"),
                "experiment_name": experiment.get("name"),
                "interval_minutes": experiment.get("interval_minutes"),
                "elapsed_seconds": max(0, int((now - started_at).total_seconds())) if started_at else None,
                "images_captured": experiment.get("images_captured"),
                "remaining_seconds": (
                    max(0, int((planned_stop_at - now).total_seconds()))
                    if planned_stop_at and state == "running"
                    else 0
                ),
                "ended_at": (
                    ended_at.isoformat(timespec="seconds")
                    if ended_at and state != "running"
                    else None
                ),
                "next_capture_at": next_capture_at.isoformat(timespec="seconds") if next_capture_at else None,
                "latest_url": latest_url,
                "folder": experiment.get("folder"),
                "end_reason": experiment.get("end_reason"),
                "has_post_notes": has_post_notes,
                "post_notes_url": notes_url,
            }
        )
    return stations


def _post_notes_payload(engine: CaptureEngine, experiment_id: str) -> dict[str, Any]:
    context = _post_notes_context(engine, experiment_id)
    notes = read_post_notes(context["folder"])
    metadata = context["metadata"]
    return {
        "experiment_id": experiment_id,
        "experiment_name": metadata.get("name"),
        "camera_label": metadata.get("camera_label"),
        "folder": str(context["folder"]),
        "metadata_notes": metadata.get("notes") or "",
        "post_notes": notes,
        "has_post_notes": bool(notes.strip()),
        "post_notes_file": str(context["folder"] / POST_NOTES_FILENAME),
        "ended_at": metadata.get("ended_at"),
        "end_reason": metadata.get("end_reason"),
        "editable": True,
    }


def _post_notes_context(engine: CaptureEngine, experiment_id: str) -> dict[str, Any]:
    folder = _experiment_folder(engine, experiment_id)
    for experiment in engine.list_experiments():
        if (
            experiment.get("experiment_id") == experiment_id
            and experiment.get("status") == "capturing"
        ):
            raise ActiveExperimentError(
                "Post-run notes are available after this experiment finishes."
            )

    metadata_path = folder / "metadata.json"
    if not metadata_path.exists():
        raise ExperimentNotFoundError(f"Experiment metadata was not found: {experiment_id}")
    try:
        metadata = read_json_file(metadata_path)
    except (json.JSONDecodeError, OSError) as exc:
        raise StorageError(f"Experiment metadata could not be read: {experiment_id}") from exc
    if not metadata.get("ended_at") or not metadata.get("end_reason"):
        raise ActiveExperimentError(
            "Post-run notes are available after this experiment finishes."
        )
    return {"folder": folder, "metadata": metadata}


def _experiment_folder(engine: CaptureEngine, experiment_id: str) -> Path:
    experiment_id = str(experiment_id or "").strip()
    if not EXPERIMENT_ID_PATTERN.fullmatch(experiment_id):
        raise ValueError("Experiment id is not valid.")

    root = engine.experiments_dir.resolve()
    folder = (root / experiment_id).resolve()
    try:
        folder.relative_to(root)
    except ValueError as exc:
        raise ValueError("Experiment id is not valid.") from exc
    if not folder.is_dir():
        raise ExperimentNotFoundError(f"Unknown experiment: {experiment_id}")
    return folder


def _wait_for_final_status(engine: CaptureEngine, experiment_id: str) -> dict[str, Any] | None:
    deadline = datetime.now().astimezone().timestamp() + 3
    while datetime.now().astimezone().timestamp() < deadline:
        for experiment in engine.list_experiments():
            if experiment.get("experiment_id") == experiment_id and experiment.get("status") != "capturing":
                return experiment
        time.sleep(0.1)
    return None


def _parse_iso(value: str) -> datetime | None:
    if not value or value == "None":
        return None
    return datetime.fromisoformat(value)


def _sort_time(experiment: dict[str, Any]) -> datetime:
    return (
        _parse_iso(str(experiment.get("started_at")))
        or _parse_iso(str(experiment.get("ended_at")))
        or datetime.min.replace(tzinfo=timezone.utc)
    )


def _idle_health_state(identity_strategy: str) -> str:
    return "ok" if identity_strategy == "hardware_id" else "identity_warning"


def _identity_health_message(identity_strategy: str) -> str | None:
    if identity_strategy == "hardware_id":
        return None
    return "Camera identity may change if cameras are replugged. Verify preview before long runs."


def _station_state_for_health(experiment: dict[str, Any], health_state: str) -> str:
    if health_state == "camera_unavailable":
        return "offline"
    if health_state == "capture_failing":
        return "error"
    if experiment.get("status") == "capturing":
        return "running"
    if experiment.get("end_reason") in {"disk_full", "storage_failed"}:
        return "error"
    return "finished"


def _camera_config_message(exc: Exception) -> str:
    text = str(exc)
    if "Missing" in text and "cameras.json" in text:
        return "Camera setup has not been completed. Run the camera setup tool first."
    return "That camera is not configured. Check camera setup and try again."


def _capture_message(exc: Exception) -> str:
    text = str(exc).lower()
    if "camera index" in text and "not detected" in text:
        return "Camera list changed. Click Detect and capture preview again."
    if "open camera" in text or "read frame" in text or "not detected" in text:
        return "Camera is not responding. Check the USB connection."
    return "Could not capture a preview. Check the camera and try again."


def _disk_space_message(exc: Exception) -> str:
    return "Not enough free disk space for this experiment. Free space or shorten the run."


def _settings_payload(engine: CaptureEngine, settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "settings": settings,
        "editable": list(EDITABLE_SETTINGS_ORDER),
        "diagnostics": {
            "experiments_dir": str(engine.experiments_dir),
            "settings_path": str(engine.settings_path),
            "cameras_path": str(engine.cameras_path),
            "allow_lan_access": bool(settings.get("allow_lan_access", False)),
            "python_version": sys.version.split()[0],
            "opencv_version": get_opencv_version(),
            "git_commit": _git_commit(PROJECT_ROOT),
        },
        "active_experiments": engine.has_active_experiments(),
    }


def _settings_error_fields(exc: SettingsError) -> dict[str, str]:
    try:
        payload = json.loads(str(exc))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def _error(
    code: str,
    message: str,
    status: int,
    *,
    fields: dict[str, str] | None = None,
) -> Response:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if fields:
        payload["error"]["fields"] = fields
    response = jsonify(payload)
    response.status_code = status
    return response
