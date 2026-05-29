from __future__ import annotations

import json
import signal
import sys
from pathlib import Path
from typing import Any

from labcam.engine import CaptureEngine
from labcam.engine.scheduler import DEFAULT_CAMERAS_PATH, DEFAULT_SETTINGS_PATH, PROJECT_ROOT
from labcam.engine.storage import atomic_write_json
from labcam.web.server import create_app


SETTINGS_EXAMPLE_PATH = PROJECT_ROOT / "config" / "settings.json.example"


def main() -> int:
    settings = _load_or_create_settings()
    if not DEFAULT_CAMERAS_PATH.exists():
        print(
            f"Missing {DEFAULT_CAMERAS_PATH}. Run `python tools/camera_setup.py setup` first.",
            file=sys.stderr,
        )
        return 1

    engine = CaptureEngine(settings_path=DEFAULT_SETTINGS_PATH, cameras_path=DEFAULT_CAMERAS_PATH)
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
    print(f"Starting Lab Imaging dashboard on http://{host}:{port}")

    _install_signal_handlers()
    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        print("Stopping Lab Imaging dashboard cleanly.", file=sys.stderr)
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

    if not SETTINGS_EXAMPLE_PATH.exists():
        raise FileNotFoundError(f"Missing settings template: {SETTINGS_EXAMPLE_PATH}")

    settings = _read_settings(SETTINGS_EXAMPLE_PATH)
    atomic_write_json(DEFAULT_SETTINGS_PATH, settings)
    print(f"Created default settings at {DEFAULT_SETTINGS_PATH}")
    return settings


def _read_settings(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected settings object in {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
