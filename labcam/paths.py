from __future__ import annotations

import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return SOURCE_ROOT


def bundled_resource_root() -> Path:
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(str(sys._MEIPASS)).resolve()
    return SOURCE_ROOT


def writable_path(*parts: str) -> Path:
    return app_root().joinpath(*parts)


def bundled_resource_path(*parts: str) -> Path:
    return bundled_resource_root().joinpath(*parts)


def settings_example_path() -> Path:
    external = writable_path("config", "settings.json.example")
    if external.exists():
        return external
    return bundled_resource_path("config", "settings.json.example")


PROJECT_ROOT = app_root()
DEFAULT_CONFIG_DIR = writable_path("config")
DEFAULT_SETTINGS_PATH = DEFAULT_CONFIG_DIR / "settings.json"
DEFAULT_CAMERAS_PATH = DEFAULT_CONFIG_DIR / "cameras.json"
DEFAULT_STATE_PATH = DEFAULT_CONFIG_DIR / "running_state.json"
DEFAULT_SETTINGS_EXAMPLE_PATH = settings_example_path()
DEFAULT_EXPERIMENTS_DIR = writable_path("experiments")
DEFAULT_LOGS_DIR = writable_path("logs")
