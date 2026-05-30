from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, url_for

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
from labcam.engine.storage import StorageError, sanitize_name


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

    @app.get("/verify-cameras")
    def verify_cameras_page() -> str:
        return render_template("verify.html")

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
            return _error("not_found", str(exc), 404)
        if latest is None or not latest.exists():
            return _error("no_frame", "No captured frame is available yet", 404)
        return send_file(latest, mimetype="image/jpeg", max_age=0)

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
            }
        )
    return stations


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


def _error(code: str, message: str, status: int) -> Response:
    response = jsonify({"error": {"code": code, "message": message}})
    response.status_code = status
    return response
