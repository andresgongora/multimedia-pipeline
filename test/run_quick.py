"""Run quick non-media smoke tests.

Usage:
    uv run test/run_quick.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TESTS = [
    ROOT / "test" / "cli" / "help.py",
    ROOT / "test" / "pipelines" / "extract_and_clean_voice.py",
    ROOT / "test" / "pipelines" / "remove_silences_and_extract_clean_voice.py",
    ROOT / "test" / "stages" / "sanitize_video.py",
]


def run_test(path: Path) -> int:
    print(f"\n>>> {path.relative_to(ROOT)}")
    result = subprocess.run([sys.executable, str(path)])
    return result.returncode


if __name__ == "__main__":
    failures = 0
    for test_file in TESTS:
        failures += 1 if run_test(test_file) else 0

    print(f"\n{'=' * 50}")
    print(f"Quick suite: {len(TESTS) - failures} passed, {failures} failed")
    sys.exit(1 if failures else 0)
