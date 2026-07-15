"""Tests: add_metadata stage.

Usage:
    uv run test/stages/add_metadata.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from stages.add_metadata import run

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


def test_embed_standard_fields() -> None:
    print("\n--- test_embed_standard_fields ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    out = OUTDIR / "add_metadata_standard_test.m4a"
    cleanup(out)

    run(
        str(SAMPLE),
        str(out),
        options={
            "fields": {"title": "Test Title", "artist": "Test Artist"},
            "verbose": False,
        },
    )

    check("output exists", out.exists())
    tags = _read_tags(out)
    check("title embedded", tags.get("title") == "Test Title", repr(tags.get("title")))
    check("artist embedded", tags.get("artist") == "Test Artist", repr(tags.get("artist")))

    cleanup(out)


def test_embed_custom_fields() -> None:
    """Standard tags and comment field must round-trip in m4a containers.

    Note: m4a uses the iTunes/MPEG-4 metadata model, which silently drops
    arbitrary uppercase keys (ORIGINAL_DURATION, SCRUBBED, etc.). Those keys
    survive in formats with richer metadata support (MKV, OGG). Here we verify
    the call succeeds and that standard-compatible fields are preserved.
    """
    print("\n--- test_embed_custom_fields ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    out = OUTDIR / "add_metadata_custom_test.m4a"
    cleanup(out)

    run(
        str(SAMPLE),
        str(out),
        options={
            "fields": {
                "comment": "youtube:dQw4w9WgXcQ",
                "ORIGINAL_DURATION": "3600.00",
            },
            "verbose": False,
        },
    )

    check("output exists", out.exists())
    tags = _read_tags(out)
    check(
        "comment embedded", tags.get("comment") == "youtube:dQw4w9WgXcQ", repr(tags.get("comment"))
    )
    # ORIGINAL_DURATION is a best-effort custom field; m4a may drop it silently
    print(
        f"  INFO  ORIGINAL_DURATION in tags: {tags.get('original_duration')!r} "
        "(m4a may drop custom uppercase keys)"
    )

    cleanup(out)


def test_preserve_existing_metadata() -> None:
    """preserve=True (default) must keep existing tags alongside new ones."""
    print("\n--- test_preserve_existing_metadata ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    # First, embed a base tag
    base = OUTDIR / "add_metadata_base.m4a"
    cleanup(base)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(SAMPLE),
            "-c",
            "copy",
            "-metadata",
            "album=BaseAlbum",
            str(base),
        ],
        capture_output=True,
        check=True,
    )

    out = OUTDIR / "add_metadata_preserve_test.m4a"
    cleanup(out)

    run(
        str(base),
        str(out),
        options={
            "fields": {"title": "New Title"},
            "preserve": True,
            "verbose": False,
        },
    )

    tags = _read_tags(out)
    check("new title present", tags.get("title") == "New Title", repr(tags.get("title")))
    check("original album preserved", tags.get("album") == "BaseAlbum", repr(tags.get("album")))

    cleanup(base)
    cleanup(out)


def test_strip_existing_metadata() -> None:
    """preserve=False must drop existing tags, keeping only the new ones."""
    print("\n--- test_strip_existing_metadata ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    base = OUTDIR / "add_metadata_strip_base.m4a"
    cleanup(base)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(SAMPLE),
            "-c",
            "copy",
            "-metadata",
            "album=ShouldBeGone",
            str(base),
        ],
        capture_output=True,
        check=True,
    )

    out = OUTDIR / "add_metadata_strip_test.m4a"
    cleanup(out)

    run(
        str(base),
        str(out),
        options={
            "fields": {"title": "Only This"},
            "preserve": False,
            "verbose": False,
        },
    )

    tags = _read_tags(out)
    check("new title present", tags.get("title") == "Only This", repr(tags.get("title")))
    check("old album gone", tags.get("album") is None, repr(tags.get("album")))

    cleanup(base)
    cleanup(out)


def test_overwrite_protection() -> None:
    print("\n--- test_overwrite_protection ---")
    if not SAMPLE.exists():
        print("  SKIP  sample file not found")
        return

    out = OUTDIR / "add_metadata_overwrite_test.m4a"
    out.write_bytes(b"dummy")
    try:
        run(str(SAMPLE), str(out), options={"fields": {"title": "x"}, "verbose": False})
        check("raises FileExistsError", False, "no exception raised")
    except FileExistsError:
        check("raises FileExistsError", True)
    finally:
        cleanup(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_embed_standard_fields()
    test_embed_custom_fields()
    test_preserve_existing_metadata()
    test_strip_existing_metadata()
    test_overwrite_protection()

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
