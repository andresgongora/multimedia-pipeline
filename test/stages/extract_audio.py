"""Test: extract_audio stage.

Usage:
    uv run test/stages/extract_audio.py                    # uses default sample
    uv run test/stages/extract_audio.py path/to/file.mp4   # custom sample
"""

from __future__ import annotations

import sys
from pathlib import Path

from stages.extract_audio import run

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


def out_path(sample: Path, suffix: str) -> Path:
    return OUTDIR / f"{sample.stem}_{suffix}"


def test_copy_codec(sample: Path):
    """Stream copy — fast, no duration guarantee."""
    print("\n--- test_copy_codec ---")
    out = out_path(sample, "test_copy.m4a")
    cleanup(out)

    result = run(str(sample), str(out))

    check("output exists", out.exists())
    check("non-empty", out.stat().st_size > 0)
    check("codec is copy", result["codec"] == "copy")
    check("padded is False", result["padded"] is False)
    check("duration reported", result["duration_s"] is not None)

    cleanup(out)


def test_lossless_codec(sample: Path):
    """WAV output must auto-select lossless and match container duration exactly."""
    print("\n--- test_lossless_codec ---")
    out = out_path(sample, "test_lossless.wav")
    cleanup(out)

    result = run(str(sample), str(out))
    container_dur = result["container_duration_s"]
    output_dur = result["duration_s"]

    check("output exists", out.exists())
    check("codec is lossless", result["codec"] == "lossless")
    check("padded is True", result["padded"] is True)

    if container_dur and output_dur:
        drift = abs(container_dur - output_dur)
        check(
            f"duration matches container (drift={drift:.4f}s)",
            drift <= 0.05,
            f"container={container_dur:.3f}s output={output_dur:.3f}s",
        )

    cleanup(out)


def test_explicit_codec(sample: Path):
    """Explicit codec choice (flac)."""
    print("\n--- test_explicit_codec ---")
    out = out_path(sample, "test_explicit.flac")
    cleanup(out)

    result = run(str(sample), str(out), options={"codec": "flac"})

    check("output exists", out.exists())
    check("codec is flac", result["codec"] == "flac")
    check("duration reported", result["duration_s"] is not None)

    cleanup(out)


def test_overwrite_protection(sample: Path):
    """Must raise FileExistsError if output exists."""
    print("\n--- test_overwrite_protection ---")
    out = out_path(sample, "test_exists.m4a")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.touch()

    try:
        run(str(sample), str(out))
        check("raises FileExistsError", False, "no exception")
    except FileExistsError:
        check("raises FileExistsError", True)

    cleanup(out)


def test_missing_input():
    """Must raise FileNotFoundError for missing input."""
    print("\n--- test_missing_input ---")
    try:
        run("/nonexistent/video.mp4", "/tmp/out.m4a")
        check("raises FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


def test_lossless_for_comparison(sample: Path):
    """Lossless WAV kept in test/output/ for manual A/B comparison."""
    print("\n--- test_lossless_for_comparison ---")
    out = OUTDIR / f"{sample.stem}_extract_audio.wav"
    cleanup(out)

    result = run(str(sample), str(out))

    check("output exists", out.exists())
    check("codec is lossless", result["codec"] == "lossless")
    # Intentionally not cleaned — kept for manual listening


if __name__ == "__main__":
    sample = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE

    if not sample.exists():
        print(f"SKIP: sample not found: {sample}")
        sys.exit(0)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"Sample: {sample}")

    test_copy_codec(sample)
    test_lossless_codec(sample)
    test_explicit_codec(sample)
    test_overwrite_protection(sample)
    test_missing_input()
    test_lossless_for_comparison(sample)

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
