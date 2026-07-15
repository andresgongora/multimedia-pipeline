"""Test: convert_to_wav stage.

Usage:
    uv run test/stages/convert_to_wav.py                    # uses default sample
    uv run test/stages/convert_to_wav.py path/to/file.m4a   # custom sample
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from stages.convert_to_wav import run

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_SAMPLE = ROOT / "test" / "sample" / "sample.m4a"
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


def probe_audio_shape(path: Path) -> tuple[int, int, str]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,codec_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    codec, sample_rate, channels = result.stdout.strip().splitlines()
    return int(sample_rate), int(channels), codec


def test_default_preserves_audio_shape(sample: Path):
    print("\n--- test_default_preserves_audio_shape ---")
    out = out_path(sample, "convert_to_wav.wav")
    cleanup(out)

    input_sr, input_channels, _ = probe_audio_shape(sample)
    result = run(str(sample), str(out))
    output_sr, output_channels, output_codec = probe_audio_shape(out)

    check("output exists", out.exists())
    check("codec reported", result["codec"] == "pcm_s16le")
    check("wav codec", output_codec == "pcm_s16le", output_codec)
    check("sample rate preserved", output_sr == input_sr, f"{input_sr} != {output_sr}")
    check(
        "channel count preserved",
        output_channels == input_channels,
        f"{input_channels} != {output_channels}",
    )

    cleanup(out)


def test_overrides(sample: Path):
    print("\n--- test_overrides ---")
    out = out_path(sample, "convert_to_wav_override.wav")
    cleanup(out)

    result = run(str(sample), str(out), options={"sample_rate": 48000, "channels": 1, "verbose": False})
    output_sr, output_channels, _ = probe_audio_shape(out)

    check("output exists", out.exists())
    check("result sample_rate", result["sample_rate"] == 48000)
    check("result channels", result["channels"] == 1)
    check("sample rate override applied", output_sr == 48000, str(output_sr))
    check("channel override applied", output_channels == 1, str(output_channels))

    cleanup(out)


def test_requires_wav_output(sample: Path):
    print("\n--- test_requires_wav_output ---")
    out = out_path(sample, "convert_to_wav_bad.m4a")
    cleanup(out)

    try:
        run(str(sample), str(out), options={"verbose": False})
        check("raises ValueError", False, "no exception")
    except ValueError:
        check("raises ValueError", True)


def test_missing_input():
    print("\n--- test_missing_input ---")
    try:
        run("/nonexistent/input.m4a", "/tmp/out.wav", options={"verbose": False})
        check("raises FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


if __name__ == "__main__":
    sample = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SAMPLE

    if not sample.exists():
        print(f"SKIP: sample not found: {sample}")
        sys.exit(0)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"Sample: {sample}")

    test_default_preserves_audio_shape(sample)
    test_overrides(sample)
    test_requires_wav_output(sample)
    test_missing_input()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
