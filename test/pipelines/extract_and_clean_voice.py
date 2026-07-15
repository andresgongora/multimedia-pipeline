"""Quick tests: extract_and_clean_voice pipeline.

Usage:
    uv run test/pipelines/extract_and_clean_voice.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pipelines.extract_and_clean_voice import run
from shared.config import load_config

ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG = ROOT / "pipelines" / "extract_and_clean_voice.yaml"

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def test_missing_input_path() -> None:
    print("\n--- test_missing_input_path ---")
    try:
        run("/definitely/nonexistent/path.mp4")
        check("raises FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


def test_config_merge_fallback() -> None:
    print("\n--- test_config_merge_fallback ---")
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "custom.yaml"
        cfg.write_text("stages:\n  clean:\n    dfn_atten: 35\n", encoding="utf-8")

        merged = load_config(_DEFAULT_CONFIG, cfg, None)

        check("keeps default video_extensions", bool(merged.get("video_extensions")))
        check("applies custom clean override", merged["stages"]["clean"].get("dfn_atten") == 35)
        check("keeps default extract codec", merged["stages"]["extract"].get("codec") == "lossless")


if __name__ == "__main__":
    test_missing_input_path()
    test_config_merge_fallback()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
