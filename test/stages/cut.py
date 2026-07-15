"""Tests: cut stage.

Usage:
    uv run test/stages/cut.py
    uv run test/stages/cut.py path/to/file.m4a
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from stages.cut import run

SAMPLE = ROOT / "test" / "sample" / "Wearing the Wrong Hat in the 1920’s Tales From the Bottle.m4a"
OUTDIR = ROOT / "test" / "output"
OUTDIR.mkdir(exist_ok=True)

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


def cleanup(p: Path) -> None:
    p.unlink(missing_ok=True)


def test_passthrough_empty_ranges() -> None:
    """Empty remove list must copy file and return passthrough=True."""
    print("\n--- test_passthrough_empty_ranges ---")
    sample = SAMPLE if SAMPLE.exists() else next((ROOT / "test" / "sample").glob("*.m4a"), None)
    if not sample:
        print("  SKIP  no .m4a sample available")
        return

    out = OUTDIR / "cut_passthrough_test.m4a"
    cleanup(out)

    result = run(str(sample), str(out), [])

    check("output exists", out.exists())
    check("passthrough flag set", result.get("passthrough") is True)
    check("removed_count is 0", result["removed_count"] == 0)
    check("output_path in result", "output_path" in result)

    cleanup(out)


def test_overwrite_protection() -> None:
    """Must raise FileExistsError if output already exists."""
    print("\n--- test_overwrite_protection ---")
    sample = SAMPLE if SAMPLE.exists() else next((ROOT / "test" / "sample").glob("*.m4a"), None)
    if not sample:
        print("  SKIP  no .m4a sample available")
        return

    out = OUTDIR / "cut_overwrite_test.m4a"
    out.write_bytes(b"dummy")
    try:
        run(str(sample), str(out), [[0.0, 1.0]])
        check("raises FileExistsError", False, "no exception raised")
    except FileExistsError:
        check("raises FileExistsError", True)
    finally:
        cleanup(out)


def test_precise_cut() -> None:
    """Cut a small range from the start of the audio."""
    print("\n--- test_precise_cut (precise mode) ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    out = OUTDIR / "cut_precise_test.m4a"
    cleanup(out)

    # Cut the first 5 seconds
    result = run(str(SAMPLE), str(out), [[0.0, 5.0]], options={"mode": "precise"})

    check("output exists", out.exists())
    check("output non-empty", out.stat().st_size > 1000)
    check("removed_count is 1", result["removed_count"] == 1)
    check("mode is precise", result["mode"] == "precise")
    check("passthrough not set", result.get("passthrough") is not True)

    # Output should be shorter than input
    import subprocess, json as _json

    def dur(p: Path) -> float:
        r = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(p),
            ],
            capture_output=True,
            text=True,
        )
        return float(r.stdout.strip())

    in_dur = dur(SAMPLE)
    out_dur = dur(out)
    check(
        f"output shorter than input ({out_dur:.1f}s < {in_dur:.1f}s)",
        out_dur < in_dur,
        f"in={in_dur:.2f} out={out_dur:.2f}",
    )

    # Keep output for manual inspection
    print(f"  INFO  output kept at {out}")


def test_fast_cut() -> None:
    """Cut in fast mode (stream copy)."""
    print("\n--- test_fast_cut (fast mode) ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    out = OUTDIR / "cut_fast_test.m4a"
    cleanup(out)

    result = run(str(SAMPLE), str(out), [[0.0, 5.0]], options={"mode": "fast"})

    check("output exists", out.exists())
    check("output non-empty", out.stat().st_size > 1000)
    check("mode is fast", result["mode"] == "fast")

    cleanup(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if sample_arg:
        SAMPLE = Path(sample_arg)

    test_passthrough_empty_ranges()
    test_overwrite_protection()
    test_precise_cut()
    test_fast_cut()

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
