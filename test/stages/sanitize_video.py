"""Test: sanitize_video stage.

Usage:
    uv run test/stages/sanitize_video.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from shared.ffprobe import get_streams
from stages.sanitize_video import _is_likely_variable_framerate, run as sanitize_video

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


def _make_sample_video(path: Path, *, width: int = 64, height: int = 32, fps: int = 10) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size={width}x{height}:rate={fps}",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:sample_rate=48000",
        "-t",
        "1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr)


def _probe_dims(path: Path) -> tuple[int | None, int | None]:
    stream = next((s for s in get_streams(path) if s.get("codec_type") == "video"), {})
    return stream.get("width"), stream.get("height")


def _probe_avg_fps(path: Path) -> float | None:
    stream = next((s for s in get_streams(path) if s.get("codec_type") == "video"), {})
    raw = stream.get("avg_frame_rate")
    if not raw or raw == "0/0":
        return None
    num, den = raw.split("/", 1)
    return float(num) / float(den)


def test_missing_input() -> None:
    print("\n--- test_missing_input ---")
    try:
        sanitize_video("/definitely/missing.mp4", "/tmp/out.mp4")
        check("raises FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


def test_passthrough_copy() -> None:
    print("\n--- test_passthrough_copy ---")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.mp4"
        dst = Path(tmp) / "dst.mp4"
        _make_sample_video(src)

        result = sanitize_video(str(src), str(dst), options={"verbose": False})

        check("output exists", dst.exists())
        check("passthrough true", result.get("passthrough") is True)
        check("copied bytes", dst.stat().st_size == src.stat().st_size)


def test_rotate_90_swaps_dimensions() -> None:
    print("\n--- test_rotate_90_swaps_dimensions ---")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.mp4"
        dst = Path(tmp) / "rotated.mp4"
        _make_sample_video(src, width=96, height=48)

        result = sanitize_video(str(src), str(dst), options={"rotate": 90, "verbose": False})

        width, height = _probe_dims(dst)
        check("output exists", dst.exists())
        check("passthrough false", result.get("passthrough") is False)
        check("dimensions swapped", (width, height) == (48, 96), f"got {(width, height)}")


def test_fix_framerate_requires_target() -> None:
    print("\n--- test_fix_framerate_requires_target ---")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.mp4"
        dst = Path(tmp) / "out.mp4"
        _make_sample_video(src)

        try:
            sanitize_video(str(src), str(dst), options={"fix_framerate": True, "verbose": False})
            check("raises ValueError", False, "no exception")
        except ValueError:
            check("raises ValueError", True)


def test_fix_framerate_sets_target() -> None:
    print("\n--- test_fix_framerate_sets_target ---")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src.mp4"
        dst = Path(tmp) / "cfr.mp4"
        _make_sample_video(src, fps=10)

        result = sanitize_video(
            str(src),
            str(dst),
            options={"fix_framerate": True, "target_fps": 30, "verbose": False},
        )

        fps = _probe_avg_fps(dst)
        check("output exists", dst.exists())
        check("passthrough false", result.get("passthrough") is False)
        check("avg fps near target", fps is not None and abs(fps - 30.0) < 0.05, f"got {fps}")


def test_vfr_detector_helper() -> None:
    print("\n--- test_vfr_detector_helper ---")
    check(
        "detects likely vfr",
        _is_likely_variable_framerate({"avg_frame_rate": "30000/1001", "r_frame_rate": "60/1"}),
    )
    check(
        "ignores matching fps",
        not _is_likely_variable_framerate({"avg_frame_rate": "30/1", "r_frame_rate": "30/1"}),
    )


if __name__ == "__main__":
    test_missing_input()
    test_passthrough_copy()
    test_rotate_90_swaps_dimensions()
    test_fix_framerate_requires_target()
    test_fix_framerate_sets_target()
    test_vfr_detector_helper()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
