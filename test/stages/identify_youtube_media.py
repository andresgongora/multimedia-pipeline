"""Tests: identify_youtube_media stage.

Depends on: scrub_metadata stage (used to prepare clean test fixtures).
Run scrub_metadata tests first to verify that stage works before relying on it here.

Usage:
    uv run test/stages/scrub_metadata.py    # verify dependency first
    uv run test/stages/identify_youtube_media.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from stages.identify_youtube_media import _extract_id_from_filename, _plausible, run
from stages.scrub_metadata import run as scrub_metadata

# Opus sample has YouTube URL embedded in its comment tag — ideal for testing
# metadata-based identification after stripping the filename clean.
SAMPLE_OPUS = (
    ROOT / "test" / "sample" / "Searching the Moon for Alien Technosignatures (160kbit_Opus).opus"
)
SAMPLE_AUDIO = (
    ROOT / "test" / "sample" / "Wearing the Wrong Hat in the 1920\u2019s Tales From the Bottle.m4a"
)
SAMPLE_VIDEO = (
    ROOT / "test" / "sample" / "Wearing the Wrong Hat in the 1920\u2019s Tales From the Bottle.mp4"
)
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


# ---------------------------------------------------------------------------
# Unit tests — filename ID extraction (no network, no files needed)
# ---------------------------------------------------------------------------


def test_extract_bracketed_id() -> None:
    print("\n--- test_extract_bracketed_id ---")
    p = Path("Rick Astley - Never Gonna Give You Up [dQw4w9WgXcQ].m4a")
    check("extracts bracketed ID", _extract_id_from_filename(p) == "dQw4w9WgXcQ")


def test_extract_url_id() -> None:
    print("\n--- test_extract_url_id ---")
    p = Path("watch?v=dQw4w9WgXcQ.mp4")
    check("extracts URL-style ID", _extract_id_from_filename(p) == "dQw4w9WgXcQ")


def test_no_id_in_filename() -> None:
    print("\n--- test_no_id_in_filename ---")
    check(
        "returns None when no ID", _extract_id_from_filename(Path("My Podcast Episode.m4a")) is None
    )


def test_plausible_rejects_words() -> None:
    print("\n--- test_plausible_rejects_words ---")
    check("rejects all-alpha token", not _plausible("QuasiStarss"))
    check("accepts token with digit", _plausible("dQw4w9WgXcQ"))


# ---------------------------------------------------------------------------
# Fixture helper — uses scrub_metadata to produce a tag-free copy
# ---------------------------------------------------------------------------


def _scrubbed_copy(src: Path, dest_name: str) -> Path:
    """Return a metadata-free copy of src at OUTDIR/dest_name using scrub_metadata."""
    dst = OUTDIR / dest_name
    cleanup(dst)
    scrub_metadata(str(src), str(dst), options={"verbose": False})
    return dst


# ---------------------------------------------------------------------------
# Integration tests — identification by filename ID (bracketed)
# ---------------------------------------------------------------------------


def test_identify_by_bracketed_id() -> None:
    """Copy sample with bracketed ID in name; must identify via filename without network."""
    print("\n--- test_identify_by_bracketed_id ---")
    sample = SAMPLE_AUDIO if SAMPLE_AUDIO.exists() else SAMPLE_VIDEO
    if not sample.exists():
        print("  SKIP  no m4a/mp4 sample available")
        return

    # Use scrub_metadata to produce a clean (tag-free) copy, then rename with ID
    scrubbed = _scrubbed_copy(sample, f"scrubbed_base{sample.suffix}")
    tmp = OUTDIR / f"test_identify [dQw4w9WgXcQ]{sample.suffix}"
    cleanup(tmp)
    scrubbed.rename(tmp)
    try:
        result = run(str(tmp), options={"verbose": False})
        check("identified", result["identified"], str(result.get("reason")))
        if result["identified"]:
            check("method is filename", result["method"] == "filename", result.get("method"))
            check("video_id correct", result["video_id"] == "dQw4w9WgXcQ")
            check("has title", bool(result.get("title")))
            check("has channel", bool(result.get("channel")))
    finally:
        cleanup(tmp)


# ---------------------------------------------------------------------------
# Integration tests — identification by embedded metadata comment URL
# ---------------------------------------------------------------------------


def test_identify_by_embedded_comment_url() -> None:
    """Opus sample has YouTube URL in comment tag; scrub name→ must find ID from metadata."""
    print("\n--- test_identify_by_embedded_comment_url ---")
    if not SAMPLE_OPUS.exists():
        print("  SKIP  opus sample not available")
        return

    # Copy with a neutral name (no ID, no recognisable title) so filename fallback won't fire
    neutral = OUTDIR / "unnamed_podcast.opus"
    cleanup(neutral)
    shutil.copy2(SAMPLE_OPUS, neutral)
    try:
        result = run(str(neutral), options={"search_fallback": False, "verbose": False})
        check("identified", result["identified"], str(result.get("reason")))
        if result["identified"]:
            check(
                "method is metadata_field",
                result["method"] == "metadata_field",
                result.get("method"),
            )
            check(
                "video_id is 2sUAWiNew2M",
                result["video_id"] == "2sUAWiNew2M",
                result.get("video_id"),
            )
            check("has title", bool(result.get("title")))
    finally:
        cleanup(neutral)


# ---------------------------------------------------------------------------
# Integration tests — title search fallback (scrubbed file, no ID anywhere)
# ---------------------------------------------------------------------------


def test_identify_search_fallback() -> None:
    """Scrubbed copy has no tags and no ID in name; must fall back to yt-dlp title search."""
    print("\n--- test_identify_search_fallback ---")
    if not SAMPLE_OPUS.exists():
        print("  SKIP  opus sample not available")
        return

    # scrub_metadata removes comment tag → no embedded ID
    # Use original filename (contains title text) so search has a chance
    scrubbed = _scrubbed_copy(
        SAMPLE_OPUS,
        "Searching the Moon for Alien Technosignatures.opus",
    )
    try:
        result = run(str(scrubbed), options={"search_fallback": True, "verbose": False})
        check("returns dict with 'identified'", "identified" in result)
        if result["identified"]:
            print(f"  INFO  identified as: {result.get('video_id')} — {result.get('title')}")
            check(
                "method is search_*",
                result["method"] in ("search_metadata", "search_filename"),
                result.get("method"),
            )
            check("has video_id", bool(result.get("video_id")))
        else:
            print(f"  INFO  not identified: {result.get('reason')} (network may be needed)")
    finally:
        cleanup(scrubbed)


def test_identify_search_disabled() -> None:
    """Scrubbed file with no ID and search_fallback=False must return not identified."""
    print("\n--- test_identify_search_disabled ---")
    if not SAMPLE_OPUS.exists():
        print("  SKIP  opus sample not available")
        return

    scrubbed = _scrubbed_copy(SAMPLE_OPUS, "unnamed_scrubbed_no_search.opus")
    try:
        result = run(str(scrubbed), options={"search_fallback": False, "verbose": False})
        check("not identified", not result["identified"])
        check("has reason", bool(result.get("reason")))
    finally:
        cleanup(scrubbed)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("NOTE: run 'uv run test/stages/scrub_metadata.py' first to verify the dependency.\n")

    test_extract_bracketed_id()
    test_extract_url_id()
    test_no_id_in_filename()
    test_plausible_rejects_words()
    test_identify_by_bracketed_id()
    test_identify_by_embedded_comment_url()
    test_identify_search_fallback()
    test_identify_search_disabled()

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
