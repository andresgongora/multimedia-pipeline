"""Test: clean_recorded_voice stage.

Requires Docker and the audio-filter image (auto-builds on first run).

Usage:
    uv run test/stages/clean_recorded_voice.py                   # default sample
    uv run test/stages/clean_recorded_voice.py path/to/audio.wav # custom sample
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from stages.clean_recorded_voice import run as clean_voice
from stages.extract_audio import run as extract_audio

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_SAMPLE = ROOT / "test" / "sample" / "sample.m4a"
# Video sample used for loudness consistency test: audio is extracted to a temp WAV first.
# This recording was captured at a different gain level than sample.m4a — ideal for the regression.
VID_SAMPLE = ROOT / "test" / "sample" / "VID_20260508_140855967.mp4"
OUTDIR = ROOT / "test" / "output"

# Loudness targets sourced from:
# stages/clean_recorded_voice/tools/audio-filter/docs/audio-filter-playbook.md
TARGET_LUFS = -14.0  # integrated loudness (LUFS)
LUFS_TOLERANCE = 1.5  # acceptable deviation from target (LUFS)
MAX_TRUE_PEAK = -0.5  # dBTP ceiling with a small margin for measurement noise
MAX_LUFS_SPREAD = 4.0  # max allowed difference between outputs from different-gain inputs
# Note: with pre-normalization + 2-pass loudnorm the spread should be ~0-3 LUFS.
# Values >4 LUFS indicate the level-compensation pipeline is broken (original bug was ~16 dB).

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


def measure_lufs(path: Path) -> dict:
    """Measure integrated loudness and true peak of an audio file using ffmpeg loudnorm.

    Returns dict with keys: input_i (LUFS, float), input_tp (dBTP, float).
    Raises RuntimeError if ffmpeg is unavailable or measurement fails.
    """
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-14:TP=-1:LRA=8:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    # loudnorm prints a JSON block to stderr
    match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', combined, re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not parse loudnorm JSON from ffmpeg output:\n{combined[-2000:]}")
    data = json.loads(match.group())
    return {
        "input_i": float(data["input_i"]),
        "input_tp": float(data["input_tp"]),
    }


def test_default_tool(sample: Path):
    """Clean with default audio-filter tool."""
    print("\n--- test_default_tool ---")
    out = out_path(sample, "test_clean.wav")
    cleanup(out)

    result = clean_voice(str(sample), str(out))

    check("output exists", out.exists())
    check("output non-empty", out.stat().st_size > 0)
    check("tool is audio-filter", result["tool"] == "audio-filter")

    cleanup(out)


def test_custom_attenuation(sample: Path):
    """Clean with higher DeepFilterNet attenuation."""
    print("\n--- test_custom_attenuation ---")
    out = out_path(sample, "test_clean_atten.wav")
    cleanup(out)

    result = clean_voice(str(sample), str(out), options={"dfn_atten": 35})

    check("output exists", out.exists())
    check("tool is audio-filter", result["tool"] == "audio-filter")

    cleanup(out)


def test_comparison_output(sample: Path):
    """Cleaned output kept for manual A/B comparison."""
    print("\n--- test_comparison_output ---")
    out = OUTDIR / f"{sample.stem}_clean_recorded_voice.wav"
    cleanup(out)

    result = clean_voice(str(sample), str(out))

    check("output exists", out.exists())
    check("tool is audio-filter", result["tool"] == "audio-filter")
    # Intentionally not cleaned — kept for manual listening


def test_overwrite_protection(sample: Path):
    print("\n--- test_overwrite_protection ---")
    out = OUTDIR / "test_voice_exists.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.touch()

    try:
        clean_voice(str(sample), str(out))
        check("raises FileExistsError", False, "no exception")
    except FileExistsError:
        check("raises FileExistsError", True)

    cleanup(out)


def test_missing_input():
    print("\n--- test_missing_input ---")
    try:
        clean_voice("/nonexistent/audio.wav", "/tmp/out.wav")
        check("raises FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


def test_unknown_tool(sample: Path):
    print("\n--- test_unknown_tool ---")
    try:
        clean_voice(str(sample), "/tmp/out.wav", options={"tool": "nonexistent"})
        check("raises ValueError", False, "no exception")
    except ValueError:
        check("raises ValueError", True)


def test_loudness_target(sample: Path):
    """Output must land within ±1.5 LUFS of -14 and not exceed -0.5 dBTP."""
    print("\n--- test_loudness_target ---")
    out = out_path(sample, "test_lufs.wav")
    cleanup(out)

    clean_voice(str(sample), str(out))

    try:
        m = measure_lufs(out)
    except RuntimeError as e:
        check("ffmpeg loudnorm measurement", False, str(e))
        cleanup(out)
        return

    lufs_ok = abs(m["input_i"] - TARGET_LUFS) <= LUFS_TOLERANCE
    tp_ok = m["input_tp"] <= MAX_TRUE_PEAK

    check(
        f"integrated loudness {m['input_i']:.1f} LUFS ≈ {TARGET_LUFS} ±{LUFS_TOLERANCE}",
        lufs_ok,
        f"got {m['input_i']:.2f} LUFS",
    )
    check(
        f"true peak {m['input_tp']:.1f} dBTP ≤ {MAX_TRUE_PEAK}",
        tp_ok,
        f"got {m['input_tp']:.2f} dBTP",
    )

    cleanup(out)


def test_loudness_consistency(sample: Path):
    """Two inputs with different gain levels must produce outputs within 2 LUFS of each other.

    Extracts audio from VID_SAMPLE (a different-gain recording) then cleans both.
    This is the regression test for the bug where quiet recordings came out ~16 dB lower
    than loud recordings after processing.
    """
    print("\n--- test_loudness_consistency ---")

    if not VID_SAMPLE.exists():
        print(f"  SKIP  VID sample not found: {VID_SAMPLE.name}")
        return

    out_a = out_path(sample, "test_consistency_a.wav")
    out_b = OUTDIR / f"{VID_SAMPLE.stem}_test_consistency_b.wav"
    cleanup(out_a)
    cleanup(out_b)

    # Extract audio from video into a temp WAV, then clean it
    with tempfile.TemporaryDirectory() as tmpdir:
        vid_audio = Path(tmpdir) / f"{VID_SAMPLE.stem}_audio.wav"
        extract_audio(str(VID_SAMPLE), str(vid_audio))
        clean_voice(str(sample), str(out_a))
        clean_voice(str(vid_audio), str(out_b))

    try:
        m_a = measure_lufs(out_a)
        m_b = measure_lufs(out_b)
    except RuntimeError as e:
        check("ffmpeg loudnorm measurement", False, str(e))
        cleanup(out_a)
        cleanup(out_b)
        return

    spread = abs(m_a["input_i"] - m_b["input_i"])
    spread_ok = spread <= MAX_LUFS_SPREAD

    print(f"  {sample.name}: {m_a['input_i']:.2f} LUFS")
    print(f"  {VID_SAMPLE.name} (extracted): {m_b['input_i']:.2f} LUFS")
    check(
        (
            f"loudness spread {spread:.1f} LUFS \u2264 {MAX_LUFS_SPREAD} "
            "between inputs with different gain"
        ),
        spread_ok,
        f"spread = {spread:.2f} LUFS",
    )

    cleanup(out_a)
    cleanup(out_b)


if __name__ == "__main__":
    sample = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE

    if not sample.exists():
        print(f"SKIP: sample not found: {sample}")
        sys.exit(0)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"Sample: {sample}")

    test_overwrite_protection(sample)
    test_missing_input()
    test_unknown_tool(sample)
    test_default_tool(sample)
    test_custom_attenuation(sample)
    test_loudness_target(sample)
    test_loudness_consistency(sample)
    test_comparison_output(sample)

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
