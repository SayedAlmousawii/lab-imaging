from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from labcam.engine import storage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_PATH = PROJECT_ROOT / "config" / "running_state.json"


class RunningStateError(RuntimeError):
    """Raised when running_state.json is malformed."""


class RunningStateManager:
    def __init__(self, state_path: Path = DEFAULT_STATE_PATH) -> None:
        self.state_path = state_path

    def read(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"running": []}

        payload = storage.read_json_file(self.state_path)
        running = payload.get("running")
        if not isinstance(running, list):
            raise RunningStateError(f"Expected running list in {self.state_path}")
        return {"running": running}

    def write(self, running: list[dict[str, Any]]) -> None:
        storage.atomic_write_json(self.state_path, {"running": running})

    def clear(self) -> None:
        self.write([])

    def replace_entry(self, entry: dict[str, Any]) -> None:
        state = self.read()
        running = [
            item
            for item in state["running"]
            if item.get("experiment_id") != entry.get("experiment_id")
        ]
        running.append(entry)
        self.write(running)

    def remove_entry(self, experiment_id: str) -> None:
        state = self.read()
        running = [item for item in state["running"] if item.get("experiment_id") != experiment_id]
        self.write(running)

    def recover_startup(self, *, experiments_dir: Path, startup_time: datetime) -> list[str]:
        state = self.read()
        recovered: list[str] = []

        for item in state["running"]:
            experiment_id = item.get("experiment_id")
            if not isinstance(experiment_id, str) or not experiment_id:
                continue

            folder_value = item.get("experiment_folder")
            if isinstance(folder_value, str) and folder_value.strip():
                folder = Path(folder_value).expanduser()
                if not folder.is_absolute():
                    folder = experiments_dir / folder
            else:
                folder = experiments_dir / experiment_id
            metadata_path = folder / "metadata.json"
            log_path = folder / "capture_log.txt"
            if not metadata_path.exists():
                continue

            metadata = storage.read_json_file(metadata_path)
            images_captured = int(metadata.get("images_captured") or item.get("images_captured") or 0)
            storage.update_metadata_finalize(
                metadata_path,
                ended_at=startup_time,
                end_reason="unknown",
                images_captured=images_captured,
            )
            storage.append_log_line(
                log_path,
                startup_time,
                "STOP",
                f"reason=unknown images={images_captured}",
            )
            recovered.append(experiment_id)

        self.clear()
        return recovered
