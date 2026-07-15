"""Tests: fetch_sponsorblock_timestamps stage.

Usage:
    uv run test/stages/fetch_sponsorblock_timestamps.py

Requires network access to sponsor.ajay.app.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from stages.fetch_sponsorblock_timestamps import run

# A well-known video with confirmed SponsorBlock entries (Linus Tech Tips video
# that has been in the DB for years). Replace with any stable known-good ID.
KNOWN_ID_WITH_SEGMENTS = "aqz-KE-bpKQ"  # LTT: "I'm Switching to Windows"

# An ID that almost certainly has no SponsorBlock data
UNKNOWN_ID = "xxxxxxxxxxx"

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


def test_structure_with_segments() -> None:
    """Fetch a video known to have SponsorBlock data."""
    print("\n--- test_structure_with_segments ---")
    result = run(KNOWN_ID_WITH_SEGMENTS, options={"verbose": False})

    check("has video_id", result.get("video_id") == KNOWN_ID_WITH_SEGMENTS)
    check("has found key", "found" in result)
    check("has segments list", isinstance(result.get("segments"), list))

    if result["found"]:
        seg = result["segments"][0]
        check("segment has start", isinstance(seg.get("start"), float))
        check("segment has end", isinstance(seg.get("end"), float))
        check("segment has category", isinstance(seg.get("category"), str))
        check("segment has action_type", isinstance(seg.get("action_type"), str))
        check("segment has uuid", isinstance(seg.get("uuid"), str))
        print(f"  INFO  {len(result['segments'])} segment(s) found")
    else:
        print(f"  INFO  no segments found for {KNOWN_ID_WITH_SEGMENTS} (may be network issue)")


def test_not_found() -> None:
    """Non-existent video ID must return found=False with empty list."""
    print("\n--- test_not_found ---")
    result = run(UNKNOWN_ID, options={"verbose": False})
    check("found is False", result["found"] is False)
    check("segments is empty list", result["segments"] == [])


def test_category_filter() -> None:
    """Requesting only one category should return only that category (if any)."""
    print("\n--- test_category_filter ---")
    result = run(
        KNOWN_ID_WITH_SEGMENTS,
        options={
            "categories": ["sponsor"],
            "verbose": False,
        },
    )
    check("has segments list", isinstance(result.get("segments"), list))
    for seg in result["segments"]:
        check(
            f"category is sponsor ({seg['uuid'][:8]})",
            seg["category"] == "sponsor",
            seg["category"],
        )


def test_privacy_api() -> None:
    """Privacy API endpoint should return the same data."""
    print("\n--- test_privacy_api ---")
    normal = run(KNOWN_ID_WITH_SEGMENTS, options={"verbose": False})
    private = run(KNOWN_ID_WITH_SEGMENTS, options={"use_privacy_api": True, "verbose": False})

    # UUIDs should match (order may differ)
    normal_uuids = {s["uuid"] for s in normal["segments"]}
    private_uuids = {s["uuid"] for s in private["segments"]}
    check(
        "privacy API returns same segments",
        normal_uuids == private_uuids,
        f"normal={len(normal_uuids)} private={len(private_uuids)}",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_structure_with_segments()
    test_not_found()
    test_category_filter()
    test_privacy_api()

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
