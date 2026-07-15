"""Test: remux_audio stage.

Usage:
    uv run test/stages/remux_audio.py                         # uses default samples
    uv run test/stages/remux_audio.py video.mp4 audio.wav     # custom samples
"""

from __future__ import annotations

import sys
from pathlib import Path

from stages.extract_audio import run as extract_audio
from stages.remux_audio import run

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_VIDEO = ROOT / "test" / "sample" / "VID_20260508_140855967.mp4"
DEFAULT_AUDIO = ROOT / "test" / "sample" / "sample.m4a"
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
    return OUTDIR / f"remux_audio_{suffix}"


def test_basic_remux(video: Path, audio: Path):
    """Replace video audio with a different audio file."""
    print("\n--- test_basic_remux ---")
    out = out_path("basic.mp4")
    cleanup(out)

    result = run(str(video), str(audio), str(out))

    check("output exists", out.exists())
    check("non-empty", out.stat().st_size > 0)
    check("output_path in result", result["output_path"] == str(out))
    check("audio_codec in result", result["audio_codec"] == "pcm_s16le")

    cleanup(out)


def test_copy_codec(video: Path, audio: Path):
    """Remux with stream-copy audio codec."""
    print("\n--- test_copy_codec ---")
    out = out_path("copy.mp4")
    cleanup(out)

    result = run(str(video), str(audio), str(out), options={"audio_codec": "copy"})

    check("output exists", out.exists())
    check("audio_codec is copy", result["audio_codec"] == "copy")

    cleanup(out)


def test_roundtrip(video: Path):
    """Extract audio from video, then remux it back — output should be valid."""
    print("\n--- test_roundtrip ---")
    temp_audio = out_path("roundtrip_audio.wav")
    out = out_path("roundtrip.mp4")
    cleanup(temp_audio)
    cleanup(out)

    extract_audio(str(video), str(temp_audio), options={"codec": "lossless"})
    result = run(str(video), str(temp_audio), str(out))

    check("output exists", out.exists())
    check("output larger than audio", out.stat().st_size > temp_audio.stat().st_size)

    cleanup(temp_audio)
    cleanup(out)


def test_overwrite_protection(video: Path, audio: Path):
    """Must refuse to overwrite existing output."""
    print("\n--- test_overwrite_protection ---")
    out = out_path("overwrite.mp4")
    cleanup(out)
    out.write_bytes(b"dummy")

    try:
        run(str(video), str(audio), str(out))
        check("raises FileExistsError", False, "no exception raised")
    except FileExistsError:
        check("raises FileExistsError", True)
    finally:
        cleanup(out)


def test_missing_video():
    """Must fail on missing video input."""
    print("\n--- test_missing_video ---")
    try:
        run("/nonexistent/video.mp4", str(DEFAULT_AUDIO), str(out_path("missing.mp4")))
        check("raises FileNotFoundError", False, "no exception raised")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


def test_missing_audio(video: Path):
    """Must fail on missing audio input."""
    print("\n--- test_missing_audio ---")
    try:
        run(str(video), "/nonexistent/audio.wav", str(out_path("missing2.mp4")))
        check("raises FileNotFoundError", False, "no exception raised")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        video = Path(sys.argv[1])
        audio = Path(sys.argv[2])
    else:
        video = DEFAULT_VIDEO
        audio = DEFAULT_AUDIO

    missing = [f for f in (video, audio) if not f.exists()]
    if missing:
        print(f"SKIP: sample(s) not found: {', '.join(str(f) for f in missing)}")
        sys.exit(0)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"Video sample: {video}")
    print(f"Audio sample: {audio}")

    test_basic_remux(video, audio)
    test_copy_codec(video, audio)
    test_roundtrip(video)
    test_overwrite_protection(video, audio)
    test_missing_video()
    test_missing_audio(video)

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
