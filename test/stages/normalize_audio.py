"""Test: normalize_audio stage.

Usage:
    uv run test/stages/normalize_audio.py                    # uses default sample
    uv run test/stages/normalize_audio.py path/to/file.wav   # custom sample
"""

from __future__ import annotations

import sys
from pathlib import Path

from stages.normalize_audio import run
from shared.ffprobe import get_streams

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_SAMPLE = ROOT / "test" / "sample" / "sample.m4a"
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


def out_path(suffix: str) -> Path:
    return OUTDIR / f"normalize_audio_{suffix}"


def test_basic_normalize(sample: Path):
    """Normalize audio with default settings."""
    print("\n--- test_basic_normalize ---")
    out = out_path("basic.wav")
    cleanup(out)

    # Probe input sample rate before normalizing
    in_streams = get_streams(sample)
    in_sr = next(
        (int(s["sample_rate"]) for s in in_streams if s.get("codec_type") == "audio" and s.get("sample_rate")),
        None,
    )

    result = run(str(sample), str(out))

    check("output exists", out.exists())
    check("non-empty", out.stat().st_size > 0)
    check("output_path in result", result["output_path"] == str(out))

    # Regression: loudnorm upsamples to 192 kHz internally; output must preserve
    # the original sample rate (fix: explicit -ar in normalize_audio.py).
    if in_sr:
        out_streams = get_streams(out)
        out_sr = next(
            (int(s["sample_rate"]) for s in out_streams if s.get("codec_type") == "audio" and s.get("sample_rate")),
            None,
        )
        check(
            f"sample rate preserved ({in_sr} Hz → {out_sr} Hz)",
            out_sr == in_sr,
            f"expected {in_sr}, got {out_sr}",
        )

    cleanup(out)


def test_custom_lufs(sample: Path):
    """Normalize to a custom LUFS target."""
    print("\n--- test_custom_lufs ---")
    out = out_path("custom_lufs.wav")
    cleanup(out)

    result = run(str(sample), str(out), options={"target_lufs": -14})

    check("output exists", out.exists())
    check("non-empty", out.stat().st_size > 0)

    cleanup(out)


def test_overwrite_protection(sample: Path):
    """Must refuse to overwrite existing output."""
    print("\n--- test_overwrite_protection ---")
    out = out_path("overwrite.wav")
    cleanup(out)
    out.write_bytes(b"dummy")

    try:
        run(str(sample), str(out))
        check("raises FileExistsError", False, "no exception raised")
    except FileExistsError:
        check("raises FileExistsError", True)
    finally:
        cleanup(out)


def test_missing_input():
    """Must fail on missing input."""
    print("\n--- test_missing_input ---")
    try:
        run("/nonexistent/audio.wav", str(out_path("missing.wav")))
        check("raises FileNotFoundError", False, "no exception raised")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


def test_for_comparison(sample: Path):
    """Keep output for manual A/B listening."""
    print("\n--- test_for_comparison ---")
    out = out_path("comparison.wav")
    cleanup(out)

    result = run(str(sample), str(out))

    check("output exists", out.exists())
    # Intentionally not cleaned — kept for manual listening


if __name__ == "__main__":
    sample = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE

    if not sample.exists():
        print(f"SKIP: sample not found: {sample}")
        sys.exit(0)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"Sample: {sample}")

    test_basic_normalize(sample)
    test_custom_lufs(sample)
    test_overwrite_protection(sample)
    test_missing_input()
    test_for_comparison(sample)

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
