"""Test: filter_podcast_audio stage.

Runs the stage against a sample opus file, checks loudness / true peak safety,
and keeps the output in test/output/ for manual A/B listening comparison.

Usage:
    uv run test/stages/filter_podcast_audio.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SAMPLE = ROOT / "test/sample/Searching the Moon for Alien Technosignatures (160kbit_Opus).opus"
OUTPUT = ROOT / "test/output/filter_podcast_audio_test.opus"
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 1.0
MAX_TRUE_PEAK = -1.5

if not SAMPLE.exists():
    print(f"SKIP — sample file not found: {SAMPLE}")
    sys.exit(0)

if OUTPUT.exists():
    OUTPUT.unlink()

MANUAL_OUTPUT = ROOT / "test/output/filter_podcast_audio_test.mp3"
if MANUAL_OUTPUT.exists():
    MANUAL_OUTPUT.unlink()

from stages.filter_podcast_audio import run  # noqa: E402


def get_audio_sample_rate(path: Path) -> int:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(result.stdout.strip())


def measure_loudness(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-14:TP=-1:LRA=7:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', combined, re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not parse loudnorm JSON from ffmpeg output:\n{combined[-2000:]}")
    data = json.loads(match.group())
    return {
        "input_i": float(data["input_i"]),
        "input_tp": float(data["input_tp"]),
    }


result = run(str(SAMPLE), str(OUTPUT))
print("Output:", result["output_path"])
assert Path(result["output_path"]).exists(), "Output file missing"

input_sr = get_audio_sample_rate(SAMPLE)
output_sr = get_audio_sample_rate(OUTPUT)
print(f"Sample rate: {input_sr} Hz -> {output_sr} Hz")
assert output_sr == input_sr, {"input_sr": input_sr, "output_sr": output_sr}

metrics = measure_loudness(OUTPUT)
print(f"Measured loudness: {metrics['input_i']:.2f} LUFS")
print(f"Measured true peak: {metrics['input_tp']:.2f} dBTP")
assert abs(metrics["input_i"] - TARGET_LUFS) <= LUFS_TOLERANCE, metrics
assert metrics["input_tp"] <= MAX_TRUE_PEAK, metrics

try:
    run(str(SAMPLE), str(MANUAL_OUTPUT), options={"output_format": "mp3", "verbose": False})
    raise AssertionError("Expected ValueError for manual lossy format without bitrate")
except ValueError:
    print("Manual lossy format without bitrate: PASS")

print("PASS")
