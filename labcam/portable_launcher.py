from __future__ import annotations

import sys

from labcam.cameras.probe import main as camera_probe_main
from labcam.main import run_dashboard


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--camera-probe":
        return camera_probe_main(sys.argv[2:])
    return run_dashboard(open_browser=True)


if __name__ == "__main__":
    raise SystemExit(main())
