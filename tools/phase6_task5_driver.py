#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from labcam.web.server import create_app


class ScenarioFailure(RuntimeError):
    pass


class _DummyEngine:
    pass


def main() -> int:
    scenarios: list[tuple[str, Callable[[], str]]] = [
        ("settings page guidance renders", scenario_settings_guidance_renders),
        ("README explains local sync pattern", scenario_readme_guidance),
        ("requirements have no cloud client dependency", scenario_requirements_no_cloud_clients),
    ]

    print("Phase 6 Task 5 driver")
    results: list[tuple[str, bool, str]] = []
    for name, run in scenarios:
        try:
            detail = run()
        except Exception as exc:
            results.append((name, False, str(exc)))
            print(f"FAIL {name}: {exc}")
        else:
            results.append((name, True, detail))
            print(f"PASS {name}: {detail}")

    passed = sum(1 for _, ok, _ in results if ok)
    print()
    print(f"Summary: {passed}/{len(results)} scenarios passed")
    for name, ok, detail in results:
        print(f"- {'PASS' if ok else 'FAIL'} {name}: {detail}")
    return 0 if passed == len(results) else 1


def scenario_settings_guidance_renders() -> str:
    app = create_app(_DummyEngine())  # type: ignore[arg-type]
    client = app.test_client()
    response = client.get("/settings")
    if response.status_code != 200:
        raise ScenarioFailure(f"Settings page failed: {response.status_code}")

    html = _normalize(response.data.decode("utf-8"))
    required = [
        "cloud backup stays outside capture",
        "onedrive",
        "google drive desktop",
        "dropbox",
        "synology drive",
        "network sync tool",
        "writes local files first",
        "continue without internet",
        "avoid browser uploads",
        "active capture",
    ]
    _require_all(html, required, "Settings page")
    return "settings storage note describes local-first sync guidance"


def scenario_readme_guidance() -> str:
    text = _normalize(_read("README.md"))
    required = [
        "cloud sync and backups",
        "does not need internet access during capture",
        "onedrive",
        "google drive desktop",
        "dropbox",
        "synology drive",
        "network sync",
        "writes each image",
        "metadata.json",
        "capture_log.txt",
        "local folder first",
        "background after they are written",
        "do not rely on browser uploads",
        "experiments should keep capturing",
        "sync can catch up later",
    ]
    _require_all(text, required, "README")
    return "README gives conservative backup instructions and offline clarity"


def scenario_requirements_no_cloud_clients() -> str:
    text = _read("requirements.txt").lower()
    forbidden_patterns = [
        r"(^|\n)\s*requests\b",
        r"(^|\n)\s*boto3\b",
        r"(^|\n)\s*botocore\b",
        r"(^|\n)\s*dropbox\b",
        r"(^|\n)\s*onedrive\b",
        r"(^|\n)\s*google-api-python-client\b",
        r"(^|\n)\s*google-auth\b",
        r"(^|\n)\s*msal\b",
        r"(^|\n)\s*paramiko\b",
    ]
    matches = [pattern for pattern in forbidden_patterns if re.search(pattern, text)]
    if matches:
        raise ScenarioFailure(f"Cloud/client dependency found in requirements.txt: {matches}")
    return "requirements remain local-only"


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _require_all(text: str, required: list[str], source: str) -> None:
    missing = [phrase for phrase in required if phrase not in text]
    if missing:
        raise ScenarioFailure(f"{source} missing guidance phrase(s): {missing}")


if __name__ == "__main__":
    raise SystemExit(main())
