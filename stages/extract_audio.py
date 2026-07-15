"""Stage: extract_audio — extract audio track from a video file using ffmpeg.

Extracts audio from a video container.

  "copy"     — Stream copy (default). Fastest, no quality loss, no re-encode.
               Duration may differ slightly from video container.

  "lossless" — Uncompressed WAV (PCM 24-bit, 48kHz, stereo). Pads audio
               with silence to exactly match the video container duration.
               Ideal for editing workflows where the audio will be processed
               separately and later re-aligned with the original video.
               Auto-selected when output path ends in .wav.

Other codecs ("flac", "aac", "mp3") are available for explicit use but do
not guarantee exact duration matching.

Inputs:
    input_path  — path to source video file
    output_path — path for extracted audio file

Options:
    codec       — "copy" (default), "lossless", "flac", "aac", "mp3"
                  When output is .wav, "copy" is automatically promoted to "lossless".
    bitrate     — target bitrate for lossy codecs, e.g. "320k" (default: None)
    sample_rate — sample rate in Hz (default: None, preserve original;
                  "lossless" forces 48000)
    channels    — number of channels (default: None, preserve original;
                  "lossless" forces 2)

Returns:
    dict with keys: output_path, codec, duration_s, container_duration_s, padded

Example usage:
    # Stream copy (fast, preserves original codec)
    result = run("video.mp4", "audio.m4a")

    # Lossless WAV — auto-selected by output extension, no option needed
    result = run("video.mp4", "audio.wav")

    # Explicit codec
    result = run("video.mp4", "audio.mp3", options={"codec": "mp3", "bitrate": "320k"})

    # CLI
    uv run -m stages.extract_audio --input video.mp4 --output audio.wav
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path

from shared.output import stage_header, stage_timer

log = logging.getLogger(__name__)

_STAGE = "extract_audio"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "codec": "copy",
    "bitrate": None,
    "sample_rate": None,
    "channels": None,
    "verbose": True,
}

_CODEC_MAP: dict[str, list[str]] = {
    "copy": ["-c:a", "copy"],
    "lossless": ["-c:a", "pcm_s24le", "-ar", "48000", "-ac", "2"],
    "flac": ["-c:a", "flac"],
    "aac": ["-c:a", "aac"],
    "mp3": ["-c:a", "libmp3lame"],
}


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------

from shared.ffprobe import get_duration


def _probe_duration(path: Path) -> float | None:
    """Return container duration in seconds via ffprobe."""
    return get_duration(path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Extract audio from video file.

    Raises:
        FileNotFoundError: if input does not exist.
        FileExistsError:   if output already exists.
        RuntimeError:      if ffmpeg fails.
    """
    opts = {**DEFAULTS, **(options or {})}
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    codec = opts["codec"]
    if codec == "copy" and dst.suffix.lower() == ".wav":
        codec = "lossless"
    if codec not in _CODEC_MAP:
        raise ValueError(f"Unknown codec '{codec}'. Choose from: {list(_CODEC_MAP.keys())}")

    container_dur = _probe_duration(src)
    pad = codec == "lossless" and container_dur is not None

    # Build ffmpeg command
    cmd = ["ffmpeg", "-i", str(src), "-vn"]
    cmd += _CODEC_MAP[codec]

    if codec not in ("copy", "lossless"):
        if opts["bitrate"]:
            cmd += ["-b:a", str(opts["bitrate"])]
        if opts["sample_rate"]:
            cmd += ["-ar", str(opts["sample_rate"])]
        if opts["channels"]:
            cmd += ["-ac", str(opts["channels"])]

    if pad:
        cmd += ["-af", "apad", "-t", f"{container_dur:.6f}"]

    cmd.append(str(dst))

    verbose = opts.get("verbose", True)
    if verbose:
        stage_header(_STAGE, src, dst, {"codec": codec})

    log.debug("ffmpeg command: %s", " ".join(cmd))

    with stage_timer(_STAGE) as ctx:
        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed (exit {result.returncode}):\n{result.stderr.strip()}")

    output_dur = _probe_duration(dst)

    ctx["detail"] = f"{output_dur:.1f}s extracted" if output_dur else "extracted"

    return {
        "output_path": str(dst),
        "codec": codec,
        "duration_s": output_dur,
        "container_duration_s": container_dur,
        "padded": pad,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli():
    parser = argparse.ArgumentParser(description="Extract audio from video file")
    parser.add_argument("--input", required=True, help="Input video file")
    parser.add_argument("--output", required=True, help="Output audio file")
    parser.add_argument("--options", default=None, help="JSON string of options")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    opts = json.loads(args.options) if args.options else None
    result = run(args.input, args.output, options=opts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
