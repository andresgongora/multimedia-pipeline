"""Tests: scrub_metadata stage.

Usage:
    uv run test/stages/scrub_metadata.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from stages.scrub_metadata import run

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


def _read_tags(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    raw = json.loads(result.stdout).get("format", {}).get("tags", {})
    return {k.lower(): v for k, v in raw.items()}


def test_strips_metadata() -> None:
    """Output must have no global metadata tags."""
    print("\n--- test_strips_metadata ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    # Embed some metadata first
    tagged = OUTDIR / "scrub_metadata_tagged_input.m4a"
    cleanup(tagged)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(SAMPLE),
            "-c",
            "copy",
            "-metadata",
            "title=Private Title",
            "-metadata",
            "comment=sensitive comment",
            "-metadata",
            "GPS=123,456",
            str(tagged),
        ],
        capture_output=True,
        check=True,
    )

    out = OUTDIR / "scrub_metadata_test.m4a"
    cleanup(out)

    run(str(tagged), str(out), options={"verbose": False})

    check("output exists", out.exists())
    check("output non-empty", out.stat().st_size > 1000)

    tags = _read_tags(out)
    check("title removed", tags.get("title") is None, repr(tags))
    check("comment removed", tags.get("comment") is None, repr(tags))

    cleanup(tagged)
    cleanup(out)


def test_audio_still_plays() -> None:
    """Output file must be a valid audio container (non-zero duration)."""
    print("\n--- test_audio_still_plays ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    out = OUTDIR / "scrub_metadata_playable_test.m4a"
    cleanup(out)

    run(str(SAMPLE), str(out), options={"verbose": False})

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    dur = float(result.stdout.strip()) if result.stdout.strip() else 0.0
    check("output has non-zero duration", dur > 0, f"duration={dur}")

    cleanup(out)


def test_overwrite_protection() -> None:
    print("\n--- test_overwrite_protection ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    out = OUTDIR / "scrub_metadata_overwrite_test.m4a"
    out.write_bytes(b"dummy")
    try:
        run(str(SAMPLE), str(out), options={"verbose": False})
        check("raises FileExistsError", False, "no exception raised")
    except FileExistsError:
        check("raises FileExistsError", True)
    finally:
        cleanup(out)


def test_strip_chapters_option() -> None:
    """strip_chapters=True must not error (may or may not change output)."""
    print("\n--- test_strip_chapters_option ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    out = OUTDIR / "scrub_metadata_chapters_test.m4a"
    cleanup(out)

    run(str(SAMPLE), str(out), options={"strip_chapters": True, "verbose": False})
    check("output exists", out.exists())

    cleanup(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_strips_metadata()
    test_audio_still_plays()
    test_overwrite_protection()
    test_strip_chapters_option()

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
