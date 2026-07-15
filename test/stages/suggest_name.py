"""Tests: suggest_name stage.

Usage:
    uv run test/stages/suggest_name.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from stages.suggest_name import run, _scrub, _from_metadata

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


# ---------------------------------------------------------------------------
# Unit tests — noise scrubbing (no files needed)
# ---------------------------------------------------------------------------


def test_scrub_codec_tokens() -> None:
    print("\n--- test_scrub_codec_tokens ---")
    result = _scrub("My Video (720p_30fps_AV1-128kbit_AAC-English)")
    check("codec tokens removed", "AV1" not in result and "AAC" not in result, repr(result))
    check("title preserved", "My Video" in result, repr(result))


def test_scrub_resolution() -> None:
    print("\n--- test_scrub_resolution ---")
    result = _scrub("Podcast Episode 1080p")
    check("resolution removed", "1080p" not in result, repr(result))
    check("title preserved", "Podcast Episode" in result, repr(result))


def test_scrub_underscores() -> None:
    print("\n--- test_scrub_underscores ---")
    result = _scrub("some_file_name")
    check("underscores → spaces", result == "some file name", repr(result))


def test_from_metadata_format() -> None:
    print("\n--- test_from_metadata_format ---")
    tags = {"title": "Never Gonna Give You Up", "artist": "Rick Astley"}
    result = _from_metadata(tags, "{artist} - {title}")
    check("formats correctly", result == "Rick Astley - Never Gonna Give You Up", repr(result))


def test_from_metadata_missing_artist() -> None:
    print("\n--- test_from_metadata_missing_artist ---")
    tags = {"title": "Never Gonna Give You Up"}
    result = _from_metadata(tags, "{artist} - {title}")
    # Should collapse the dangling " - " and just return the title
    check("no dangling separator", " - " not in result.strip(" -"), repr(result))
    check("title present", "Never Gonna Give You Up" in result, repr(result))


def test_from_metadata_empty_tags() -> None:
    print("\n--- test_from_metadata_empty_tags ---")
    result = _from_metadata({}, "{artist} - {title}")
    check("returns empty string", result == "", repr(result))


# ---------------------------------------------------------------------------
# Integration tests — sample file
# ---------------------------------------------------------------------------


def test_suggest_from_sample_file() -> None:
    """Run against the sample file; strategy may be 'scrub' or 'metadata'."""
    print("\n--- test_suggest_from_sample_file ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    result = run(str(SAMPLE), options={"verbose": False})
    check("has suggested_name", bool(result.get("suggested_name")))
    check("has strategy", result.get("strategy") in ("metadata", "scrub", "none"))
    print(f"  INFO  suggested: {result['suggested_name']!r} (strategy={result['strategy']})")


def test_suggest_from_tagged_file() -> None:
    """Create a temp file with metadata tags, confirm metadata strategy is used."""
    print("\n--- test_suggest_from_tagged_file ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    tmp = OUTDIR / "suggest_name_tagged_test.m4a"
    tmp.unlink(missing_ok=True)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(SAMPLE),
            "-c",
            "copy",
            "-metadata",
            "title=Test Title",
            "-metadata",
            "artist=Test Artist",
            str(tmp),
        ],
        capture_output=True,
        check=True,
    )
    try:
        result = run(str(tmp), options={"verbose": False})
        check("strategy is metadata", result["strategy"] == "metadata", result.get("strategy"))
        check(
            "name contains title",
            "Test Title" in result["suggested_name"],
            result["suggested_name"],
        )
        check(
            "name contains artist",
            "Test Artist" in result["suggested_name"],
            result["suggested_name"],
        )
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_scrub_codec_tokens()
    test_scrub_resolution()
    test_scrub_underscores()
    test_from_metadata_format()
    test_from_metadata_missing_artist()
    test_from_metadata_empty_tags()
    test_suggest_from_sample_file()
    test_suggest_from_tagged_file()

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
