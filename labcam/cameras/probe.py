from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from labcam.cameras.interface import camera_info_to_dict, list_cameras, preview_frame, save_jpeg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fresh-process camera probe.")
    parser.add_argument("--preview-index", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--quality", type=int)
    args = parser.parse_args(argv)

    if args.preview_index is not None:
        if args.output is None:
            raise SystemExit("--output is required with --preview-index")
        camera = _camera_for_index(args.preview_index)
        output_path = save_jpeg(preview_frame(camera), args.output, quality=args.quality)
        json.dump({"preview_path": str(output_path)}, sys.stdout)
        sys.stdout.write("\n")
        return 0

    payload = {"cameras": [camera_info_to_dict(camera) for camera in list_cameras()]}
    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")
    return 0


def _camera_for_index(camera_index: int):
    for camera in list_cameras():
        if camera.index == camera_index:
            return camera
    raise RuntimeError(f"Camera index {camera_index} is not detected.")


if __name__ == "__main__":
    raise SystemExit(main())
