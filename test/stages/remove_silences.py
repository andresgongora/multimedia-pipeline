"""Test: remove_silences stage.

Requires Docker and the silence-remover image (auto-builds on first run).

Usage:
    uv run test/stages/remove_silences.py                              # default sample
    uv run test/stages/remove_silences.py test/sample/VID_20260508_140855967.mp4
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from stages.remove_silences import run as remove_silences
from shared.ffprobe import get_codec_names

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


def out_path(sample: Path, suffix: str) -> Path:
    return OUTDIR / f"{sample.stem}_{suffix}"


def test_overwrite_protection(sample: Path):
    print("\n--- test_overwrite_protection ---")
    out = OUTDIR / "test_silence_exists.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.touch()

    try:
        remove_silences(str(sample), str(out))
        check("raises FileExistsError", False, "no exception")
    except FileExistsError:
        check("raises FileExistsError", True)

    cleanup(out)


def test_missing_input():
    print("\n--- test_missing_input ---")
    try:
        remove_silences("/nonexistent/video.mp4", "/tmp/out.mp4")
        check("raises FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


def test_unknown_method(sample: Path):
    print("\n--- test_unknown_method ---")
    try:
        remove_silences(str(sample), "/tmp/out.mp4", options={"method": "nonexistent"})
        check("raises ValueError", False, "no exception")
    except ValueError:
        check("raises ValueError", True)


def test_detect_and_cut_not_implemented(sample: Path):
    print("\n--- test_detect_and_cut_not_implemented ---")
    out = out_path(sample, "test_dac.mp4")
    try:
        remove_silences(str(sample), str(out), options={"method": "detect-and-cut"})
        check("raises NotImplementedError", False, "no exception")
    except NotImplementedError:
        check("raises NotImplementedError", True)


def test_default_method(sample: Path):
    """Remove silences with default auto-editor method."""
    print("\n--- test_default_method ---")
    out = out_path(sample, "test_no_silence.mp4")
    cleanup(out)

    result = remove_silences(str(sample), str(out))

    check("output exists", out.exists())
    check("output non-empty", out.stat().st_size > 0)
    check("method is auto-editor", result["method"] == "auto-editor")

    # Output should be shorter than input (silences removed)
    in_size = Path(str(sample)).stat().st_size
    out_size = out.stat().st_size
    check("output smaller than input", out_size < in_size, f"in={in_size} out={out_size}")

    # Audio must be container-compatible (not raw PCM in MP4)
    audio_codec = _probe_audio_codec(out)
    check(
        f"audio codec compatible (got: {audio_codec})",
        audio_codec not in (None, "pcm_s16le", "pcm_s24le", "pcm_s32le"),
        f"got: {audio_codec}",
    )

    cleanup(out)


def test_custom_threshold(sample: Path):
    """Remove silences with lower threshold (more aggressive)."""
    print("\n--- test_custom_threshold ---")
    out = out_path(sample, "test_no_silence_aggr.mp4")
    cleanup(out)

    result = remove_silences(
        str(sample), str(out), options={"threshold": 0.05, "margin": "0.15sec"}
    )

    check("output exists", out.exists())
    check("method is auto-editor", result["method"] == "auto-editor")

    cleanup(out)


def test_comparison_output(sample: Path):
    """Output kept for manual A/B comparison."""
    print("\n--- test_comparison_output ---")
    out = OUTDIR / f"{sample.stem}_remove_silences{sample.suffix}"
    cleanup(out)

    result = remove_silences(str(sample), str(out))

    check("output exists", out.exists())
    check("method is auto-editor", result["method"] == "auto-editor")

    # Verify audio codec is not raw PCM (ipcm) — would be unplayable in most players
    audio_codec = _probe_audio_codec(out)
    check(
        f"audio codec playable (got: {audio_codec})",
        audio_codec not in (None, "pcm_s16le", "pcm_s24le", "pcm_s32le"),
        f"got: {audio_codec}",
    )
    # Intentionally not cleaned — kept for manual comparison


def test_audio_codec_with_normalize(sample: Path):
    """Audio codec must be container-compatible even when normalize=True (default).

    Regression test: when normalize=True, audio goes through remux_audio (which
    defaults to pcm_s16le). auto-editor then received a pcm-audio input and
    propagated ipcm to the output. Fix: entrypoint.sh forces -c:a aac.
    """
    print("\n--- test_audio_codec_with_normalize ---")
    out = out_path(sample, "test_codec_normalize.mp4")
    cleanup(out)

    remove_silences(str(sample), str(out), options={"normalize": True})

    audio_codec = _probe_audio_codec(out)
    check("output exists", out.exists())
    check(
        f"audio codec not raw PCM (got: {audio_codec})",
        audio_codec not in (None, "pcm_s16le", "pcm_s24le", "pcm_s32le"),
        f"expected aac/mp3/opus, got: {audio_codec}",
    )

    cleanup(out)


def _probe_rotation(path: Path) -> str | None:
    """Get rotation from video stream side data via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream_side_data=rotation",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    val = result.stdout.strip()
    return val if val else None


def _probe_audio_codec(path: Path) -> str | None:
    """Get audio stream codec_name via ffprobe."""
    codecs = get_codec_names(path)
    return codecs.get("audio")


def test_rotation_preserved(sample: Path):
    """Rotation metadata from source must be preserved after silence removal."""
    print("\n--- test_rotation_preserved ---")
    src_rotation = _probe_rotation(sample)
    if not src_rotation or src_rotation == "0":
        print("  SKIP  sample has no rotation metadata")
        return

    out = out_path(sample, "test_rotation.mp4")
    cleanup(out)

    remove_silences(str(sample), str(out), options={"normalize": False})

    out_rotation = _probe_rotation(out)
    check("output exists", out.exists())
    check(f"rotation preserved ({src_rotation}° -> {out_rotation}°)", out_rotation == src_rotation)

    cleanup(out)


if __name__ == "__main__":
    sample = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE

    if not sample.exists():
        print(f"SKIP: sample not found: {sample}")
        sys.exit(0)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"Sample: {sample}")

    # Fast tests first
    test_overwrite_protection(sample)
    test_missing_input()
    test_unknown_method(sample)
    test_detect_and_cut_not_implemented(sample)

    # Docker tests (slow)
    test_default_method(sample)
    test_rotation_preserved(sample)
    test_custom_threshold(sample)
    test_audio_codec_with_normalize(sample)
    test_comparison_output(sample)

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
