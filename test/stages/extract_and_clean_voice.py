"""Test: extract_and_clean_voice stage.

Requires Docker and the audio-filter image.
Input must be a video file (extracts audio first).

Usage:
    uv run test/stages/extract_and_clean_voice.py                    # default sample
    uv run test/stages/extract_and_clean_voice.py path/to/video.mp4  # custom sample
"""

from __future__ import annotations

import sys
from pathlib import Path

from stages.extract_and_clean_voice import run

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_SAMPLE = ROOT / "test" / "sample" / "VID_20260508_140855967.mp4"
OUTDIR = ROOT / "test" / "output"

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def cleanup(path: Path):
    if path.exists():
        path.unlink()


def test_full_pipeline(sample: Path):
    """Extract lossless + clean voice, keep output for manual comparison."""
    print("\n--- test_full_pipeline ---")
    out = OUTDIR / f"{sample.stem}_extract_and_clean_voice.wav"
    cleanup(out)

    result = run(str(sample), str(out))

    check("output exists", out.exists())
    check("output non-empty", out.stat().st_size > 0)
    check("extract codec is lossless", result["extract_result"]["codec"] == "lossless")
    check("clean tool is audio-filter", result["clean_result"]["tool"] == "audio-filter")

    # Check temp files were cleaned
    temps = list(OUTDIR.glob(".~*~*"))
    check("no temp files left", len(temps) == 0, f"found: {temps}")

    # Intentionally not cleaned — kept for manual listening


def test_overwrite_protection(sample: Path):
    print("\n--- test_overwrite_protection ---")
    out = OUTDIR / "test_eacv_exists.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.touch()

    try:
        run(str(sample), str(out))
        check("raises FileExistsError", False, "no exception")
    except FileExistsError:
        check("raises FileExistsError", True)

    cleanup(out)


def test_missing_input():
    print("\n--- test_missing_input ---")
    try:
        run("/nonexistent/video.mp4", "/tmp/out.wav")
        check("raises FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


if __name__ == "__main__":
    sample = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE

    if not sample.exists():
        print(f"SKIP: sample not found: {sample}")
        sys.exit(0)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"Sample: {sample}")

    test_overwrite_protection(sample)
    test_missing_input()
    test_full_pipeline(sample)

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
