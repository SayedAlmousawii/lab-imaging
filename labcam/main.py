from __future__ import annotations

import json
import signal
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

from labcam.engine import CaptureEngine
from labcam.engine.scheduler import DEFAULT_CAMERAS_PATH, DEFAULT_SETTINGS_PATH
from labcam.engine.storage import atomic_write_json
from labcam.paths import DEFAULT_SETTINGS_EXAMPLE_PATH
from labcam.web.server import create_app


def main() -> int:
    return run_dashboard(open_browser=False)


def run_dashboard(*, open_browser: bool, browser_timeout_seconds: float = 20.0) -> int:
    settings = _load_or_create_settings()
    if not DEFAULT_CAMERAS_PATH.exists():
        print(
            f"Missing {DEFAULT_CAMERAS_PATH}. Open the dashboard Cameras page or run "
            "`python tools/camera_setup.py setup`.",
            file=sys.stderr,
        )

    engine = CaptureEngine(settings_path=DEFAULT_SETTINGS_PATH, cameras_path=DEFAULT_CAMERAS_PATH)
    if DEFAULT_CAMERAS_PATH.exists():
        for camera in engine.list_cameras():
            unavailable_message = engine.camera_unavailable_message(camera)
            if unavailable_message:
                print(
                    f"WARNING: {camera.label} is unavailable. {unavailable_message}",
                    file=sys.stderr,
                )
    engine.start()
    app = create_app(engine)

    allow_lan_access = bool(settings.get("allow_lan_access", False))
    host = "0.0.0.0" if allow_lan_access else "127.0.0.1"
    port = int(settings.get("web_port", 5000))
    if allow_lan_access:
        print(
            "WARNING: LAN access is enabled and the v1 dashboard has no authentication. "
            "Only use this on a trusted lab network.",
            file=sys.stderr,
        )
    local_url = f"http://127.0.0.1:{port}"
    if not _port_available(host, port):
        print(
            f"Could not start Lab Imaging because port {port} is already in use. "
            "Close the other Lab Imaging window or change web_port in config/settings.json.",
            file=sys.stderr,
        )
        engine.shutdown_cleanly()
        return 2

    print(f"Starting Lab Imaging dashboard on http://{host}:{port}")
    if open_browser:
        _open_browser_when_ready(local_url, timeout_seconds=browser_timeout_seconds)

    _install_signal_handlers()
    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("Stopping Lab Imaging dashboard cleanly.", file=sys.stderr)
    except OSError as exc:
        print(f"Could not start Lab Imaging dashboard: {exc}", file=sys.stderr)
        return 2
    finally:
        engine.shutdown_cleanly()
    return 0


def _install_signal_handlers() -> None:
    def request_exit(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    for signal_name in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, signal_name, None)
        if signum is not None:
            signal.signal(signum, request_exit)


def _load_or_create_settings() -> dict[str, Any]:
    if DEFAULT_SETTINGS_PATH.exists():
        return _read_settings(DEFAULT_SETTINGS_PATH)

    if not DEFAULT_SETTINGS_EXAMPLE_PATH.exists():
        raise FileNotFoundError(f"Missing settings template: {DEFAULT_SETTINGS_EXAMPLE_PATH}")

    settings = _read_settings(DEFAULT_SETTINGS_EXAMPLE_PATH)
    atomic_write_json(DEFAULT_SETTINGS_PATH, settings)
    print(f"Created default settings at {DEFAULT_SETTINGS_PATH}")
    return settings


def _read_settings(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected settings object in {path}")
    return payload


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            return False
    return True


def _open_browser_when_ready(url: str, *, timeout_seconds: float) -> None:
    thread = threading.Thread(
        target=_wait_for_dashboard_then_open,
        args=(url, timeout_seconds),
        daemon=True,
    )
    thread.start()


def _wait_for_dashboard_then_open(url: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status < 500:
                    print(f"Opening dashboard in your browser: {url}")
                    webbrowser.open(url)
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)

    print(
        f"Lab Imaging started, but the dashboard did not answer within "
        f"{timeout_seconds:.0f} seconds. Open {url} manually.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
