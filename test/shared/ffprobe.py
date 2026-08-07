"""Tests: shared/ffprobe.py — media probing helpers.

Generates synthetic audio/video with ffmpeg lavfi so no sample fixtures needed.

Usage:
    uv run test/shared/ffprobe.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.ffprobe import (
    get_audio_bitrate,
    get_codec_names,
    get_duration,
    get_duration_strict,
    get_format,
    get_format_and_streams,
    get_streams,
    get_tags,
    has_video_stream,
)

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


def _make_audio(path: Path, *, duration: float = 2.0, sample_rate: int = 48000, channels: int = 2) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:sample_rate={sample_rate}:duration={duration}",
        "-ac", str(channels),
        "-c:a", "aac",
        "-b:a", "128k",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)


def _make_video(path: Path, *, duration: float = 1.0, width: int = 64, height: int = 32) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000",
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)


def _make_tagged_audio(path: Path) -> None:
    _make_audio(path)
    tagged = path.with_suffix(".tagged.m4a")
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-c", "copy",
        "-metadata", "title=TestTitle",
        "-metadata", "artist=TestArtist",
        str(tagged),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    path.unlink()
    tagged.rename(path)


def test_get_duration() -> None:
    print("\n--- test_get_duration ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "audio.m4a"
        _make_audio(f, duration=2.0)
        dur = get_duration(f)
        check("returns float", isinstance(dur, float))
        check("duration ~2s", dur is not None and abs(dur - 2.0) < 0.5, f"got {dur}")


def test_get_duration_missing() -> None:
    print("\n--- test_get_duration_missing ---")
    result = get_duration(Path("/nonexistent/file.m4a"))
    check("returns None for missing", result is None)


def test_get_duration_strict() -> None:
    print("\n--- test_get_duration_strict ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "audio.m4a"
        _make_audio(f, duration=1.5)
        dur = get_duration_strict(f)
        check("returns float", isinstance(dur, float))
        check("duration ~1.5s", abs(dur - 1.5) < 0.5, f"got {dur}")


def test_get_duration_strict_missing() -> None:
    print("\n--- test_get_duration_strict_missing ---")
    try:
        get_duration_strict(Path("/nonexistent/file.m4a"))
        check("raises on missing", False, "no exception")
    except (subprocess.CalledProcessError, Exception):
        check("raises on missing", True)


def test_has_video_stream_true() -> None:
    print("\n--- test_has_video_stream_true ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "video.mp4"
        _make_video(f)
        check("video file has video stream", has_video_stream(f) is True)


def test_has_video_stream_false() -> None:
    print("\n--- test_has_video_stream_false ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "audio.m4a"
        _make_audio(f)
        check("audio file has no video stream", has_video_stream(f) is False)


def test_get_streams() -> None:
    print("\n--- test_get_streams ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "video.mp4"
        _make_video(f)
        streams = get_streams(f)
        check("returns list", isinstance(streams, list))
        check("has streams", len(streams) > 0)
        types = {s.get("codec_type") for s in streams}
        check("has video stream", "video" in types)
        check("has audio stream", "audio" in types)


def test_get_streams_missing() -> None:
    print("\n--- test_get_streams_missing ---")
    result = get_streams(Path("/nonexistent/file.mp4"))
    check("returns empty list", result == [])


def test_get_format() -> None:
    print("\n--- test_get_format ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "audio.m4a"
        _make_audio(f)
        fmt = get_format(f)
        check("returns dict", isinstance(fmt, dict))
        check("has format_name", "format_name" in fmt, str(list(fmt.keys())))


def test_get_format_missing() -> None:
    print("\n--- test_get_format_missing ---")
    result = get_format(Path("/nonexistent/file.m4a"))
    check("returns empty dict", result == {})


def test_get_format_and_streams() -> None:
    print("\n--- test_get_format_and_streams ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "video.mp4"
        _make_video(f)
        fmt, streams = get_format_and_streams(f)
        check("format is dict", isinstance(fmt, dict))
        check("streams is list", isinstance(streams, list))
        check("format non-empty", len(fmt) > 0)
        check("streams non-empty", len(streams) > 0)


def test_get_tags() -> None:
    print("\n--- test_get_tags ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "tagged.m4a"
        _make_tagged_audio(f)
        tags = get_tags(f)
        check("returns dict", isinstance(tags, dict))
        check("title tag found", tags.get("title") == "TestTitle", repr(tags.get("title")))
        check("artist tag found", tags.get("artist") == "TestArtist", repr(tags.get("artist")))
        check("keys lowercase", all(k == k.lower() for k in tags))


def test_get_tags_no_tags() -> None:
    print("\n--- test_get_tags_no_tags ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "audio.m4a"
        _make_audio(f)
        tags = get_tags(f)
        check("returns dict", isinstance(tags, dict))


def test_get_audio_bitrate() -> None:
    print("\n--- test_get_audio_bitrate ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "audio.m4a"
        _make_audio(f)
        br = get_audio_bitrate(f)
        check("returns int or None", br is None or isinstance(br, int))
        if br is not None:
            check("bitrate reasonable", 64000 <= br <= 256000, f"got {br}")


def test_get_audio_bitrate_missing() -> None:
    print("\n--- test_get_audio_bitrate_missing ---")
    result = get_audio_bitrate(Path("/nonexistent/file.m4a"))
    check("returns None for missing", result is None)


def test_get_codec_names() -> None:
    print("\n--- test_get_codec_names ---")
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "video.mp4"
        _make_video(f)
        codecs = get_codec_names(f)
        check("returns dict", isinstance(codecs, dict))
        check("has video codec", "video" in codecs, repr(codecs))
        check("has audio codec", "audio" in codecs, repr(codecs))


if __name__ == "__main__":
    test_get_duration()
    test_get_duration_missing()
    test_get_duration_strict()
    test_get_duration_strict_missing()
    test_has_video_stream_true()
    test_has_video_stream_false()
    test_get_streams()
    test_get_streams_missing()
    test_get_format()
    test_get_format_missing()
    test_get_format_and_streams()
    test_get_tags()
    test_get_tags_no_tags()
    test_get_audio_bitrate()
    test_get_audio_bitrate_missing()
    test_get_codec_names()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
