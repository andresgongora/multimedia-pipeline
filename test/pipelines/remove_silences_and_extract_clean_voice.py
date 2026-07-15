"""Quick tests: remove_silences_and_extract_clean_voice pipeline.

Usage:
    uv run test/pipelines/remove_silences_and_extract_clean_voice.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pipelines.remove_silences_and_extract_clean_voice import (
    _resolve_audio_output,
    _resolve_video_output,
    run,
)
from shared.config import load_config

ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CONFIG = ROOT / "pipelines" / "remove_silences_and_extract_clean_voice.yaml"

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
        cfg.write_text(
            "output:\n  video_suffix: .trimmed\nstages:\n  remove:\n    threshold: 0.02\n",
            encoding="utf-8",
        )

        merged = load_config(_DEFAULT_CONFIG, cfg, None)

        check("keeps default video_extensions", bool(merged.get("video_extensions")))
        check("applies custom video suffix", merged["output"].get("video_suffix") == ".trimmed")
        check(
            "keeps sanitize vfr warning default",
            merged["stages"]["sanitize"].get("warn_variable_framerate") is True,
        )
        check("applies custom remove override", merged["stages"]["remove"].get("threshold") == 0.02)
        check("keeps default extract codec", merged["stages"]["extract"].get("codec") == "lossless")


def test_output_naming() -> None:
    print("\n--- test_output_naming ---")
    source = Path("/tmp/demo clip.mp4")
    trimmed = _resolve_video_output(source, ".silences_removed")
    cleaned = _resolve_audio_output(trimmed, ".cleaned_voice", input_file=source)

    check("trimmed video keeps folder", trimmed.parent == source.parent)
    check("trimmed video adds suffix", trimmed.name == "demo clip.silences_removed.mp4")
    check(
        "cleaned audio derives from trimmed stem",
        cleaned.name == "demo clip.silences_removed.cleaned_voice.wav",
    )


if __name__ == "__main__":
    test_missing_input_path()
    test_config_merge_fallback()
    test_output_naming()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
