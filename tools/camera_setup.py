#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labcam.cameras.interface import CameraInfo, capture_frame, list_cameras, preview_frame, save_jpeg


CAMERAS_CONFIG_PATH = PROJECT_ROOT / "config" / "cameras.json"
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


def main() -> int:
    parser = argparse.ArgumentParser(description="List, preview, label, and stress-test cameras.")
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="List detected cameras.")
    add_index_filter(list_parser)

    setup_parser = subparsers.add_parser("setup", help="Preview each camera and save config/cameras.json.")
    add_index_filter(setup_parser)

    stress_parser = subparsers.add_parser(
        "stress-test",
        help="Run repeated open-grab-close captures for each detected camera.",
    )
    add_index_filter(stress_parser)
    stress_parser.add_argument(
        "--cycles",
        type=int,
        default=100,
        help="Capture cycles per camera. Defaults to the Phase 1 required 100.",
    )

    args = parser.parse_args()
    command = args.command or "setup"

    if command == "list":
        return list_command(args.indexes)
    if command == "setup":
        return setup_command(args.indexes)
    if command == "stress-test":
        return stress_test_command(args.cycles, args.indexes)

    parser.error(f"Unknown command: {command}")
    return 2


def list_command(indexes: list[int] | None = None) -> int:
    cameras = selected_cameras(indexes)
    if not cameras:
        print("No cameras detected.")
        return 1

    print_cameras(cameras)
    return 0


def setup_command(indexes: list[int] | None = None) -> int:
    cameras = selected_cameras(indexes)
    if not cameras:
        print("No cameras detected. Check camera permissions, USB connections, and macOS privacy settings.")
        return 1

    print_cameras(cameras)
    records = []

    for number, camera in enumerate(cameras, start=1):
        print()
        print(f"Camera {number}: {camera.label} (OpenCV index {camera.index})")
        _print_warnings(camera)

        input("Press Enter to capture a fresh preview snapshot...")
        preview = preview_frame(camera)
        preview_path = _preview_path(camera.index)
        save_jpeg(preview, preview_path)
        print(f"Preview snapshot: {preview_path.resolve()}")

        label = _prompt_label(default=f"station{number}")
        notes = input("Optional notes: ").strip()

        records.append(
            {
                "label": label,
                "identity_strategy": camera.identity_strategy,
                "stable_id": camera.stable_id,
                "last_seen_index": camera.index,
                "warnings": camera.warnings,
                "notes": notes,
            }
        )

    CAMERAS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CAMERAS_CONFIG_PATH.open("w", encoding="utf-8") as config_file:
        json.dump({"cameras": records}, config_file, indent=2)
        config_file.write("\n")

    print()
    print(f"Saved camera mapping: {CAMERAS_CONFIG_PATH.resolve()}")
    return 0


def stress_test_command(cycles: int, indexes: list[int] | None = None) -> int:
    if cycles < 1:
        print("--cycles must be at least 1")
        return 2

    cameras = selected_cameras(indexes)
    if not cameras:
        print("No cameras detected. Stress test cannot run.")
        return 1

    failures: list[str] = []
    for camera in cameras:
        print(f"Stress testing {camera.label} (index {camera.index}) for {cycles} cycles...", flush=True)
        for cycle in range(1, cycles + 1):
            try:
                capture_frame(camera)
            except Exception as exc:
                failures.append(f"{camera.label} index={camera.index} cycle={cycle}: {exc}")
                print(f"  FAIL cycle {cycle}: {exc}", flush=True)
                break
            if cycle == 1 or cycle % 10 == 0 or cycle == cycles:
                print(f"  ok {cycle}/{cycles}", flush=True)

    if failures:
        print()
        print("Stress test failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print()
    print("Stress test passed.")
    return 0


def print_cameras(cameras: list[CameraInfo]) -> None:
    for number, camera in enumerate(cameras, start=1):
        print(
            f"{number}. {camera.label} | index={camera.index} | "
            f"identity_strategy={camera.identity_strategy} | stable_id={camera.stable_id}"
        )
        _print_warnings(camera)


def add_index_filter(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--indexes",
        type=int,
        nargs="+",
        help="Limit the command to specific OpenCV indexes, for example: --indexes 0 1",
    )


def selected_cameras(indexes: list[int] | None) -> list[CameraInfo]:
    cameras = list_cameras()
    if indexes is None:
        return cameras

    requested = set(indexes)
    selected = [camera for camera in cameras if camera.index in requested]
    found = {camera.index for camera in selected}
    missing = sorted(requested - found)
    if missing:
        missing_text = ", ".join(str(index) for index in missing)
        raise SystemExit(f"Requested camera index(es) not detected: {missing_text}")

    return selected


def _print_warnings(camera: CameraInfo) -> None:
    for warning in camera.warnings:
        print(f"   WARNING: {warning}")


def _prompt_label(*, default: str) -> str:
    while True:
        entered = input(f"Label [{default}]: ").strip() or default
        if LABEL_PATTERN.fullmatch(entered):
            return entered

        print("Use only alphanumeric characters and hyphens. No spaces or slashes.")


def _preview_path(camera_index: int) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(tempfile.gettempdir()) / f"labcam-preview-camera{camera_index}-{timestamp}.jpg"


if __name__ == "__main__":
    raise SystemExit(main())
