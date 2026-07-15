"""Stage: convert_to_wav — convert a media file's primary audio stream to lossless WAV.

Takes any media file with audio (audio-only or video) and writes a WAV working
file for downstream editing. Intended for pipelines that want all destructive
edits to happen on a lossless intermediate before a final lossy encode.

By default the stage preserves the source audio sample rate and channel count.
This avoids unnecessary resampling before later edit stages. Optional overrides
exist when a caller explicitly wants a fixed WAV shape.

Inputs:
    input_path  — path to source media file with audio
    output_path — path for WAV output file

Options:
    sample_rate — output sample rate in Hz (default: preserve source, fallback 48000)
    channels    — output channel count (default: preserve source, fallback 2)
    sample_fmt  — ffmpeg PCM sample format / codec name (default: "pcm_s16le")
    verbose     — print progress (default: True)

Returns:
    dict with keys: output_path, codec, sample_rate, channels

Example usage:
    from stages.convert_to_wav import run

    result = run("episode.m4a", "episode_work.wav")
    result = run("video.mp4", "video_audio.wav", options={"sample_rate": 48000})

    # CLI
    uv run -m stages.convert_to_wav --input episode.m4a --output episode_work.wav
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path

from shared.ffprobe import get_streams
from shared.output import stage_header, stage_timer

log = logging.getLogger(__name__)

_STAGE = "convert_to_wav"


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "sample_rate": None,
    "channels": None,
    "sample_fmt": "pcm_s16le",
    "verbose": True,
}


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------


def _probe_audio_shape(src: Path) -> tuple[int, int]:
    """Return (sample_rate, channels) for the first audio stream."""
    streams = get_streams(src)
    for stream in streams:
        if stream.get("codec_type") != "audio":
            continue
        sample_rate = int(stream.get("sample_rate") or 48000)
        channels = int(stream.get("channels") or 2)
        return sample_rate, channels
    raise RuntimeError(f"No audio stream found: {src}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Convert primary audio stream to lossless WAV.

    Raises:
        FileNotFoundError: if input does not exist.
        FileExistsError:   if output already exists.
        ValueError:        if output path is not .wav.
        RuntimeError:      if no audio stream exists or ffmpeg fails.
    """
    opts = {**DEFAULTS, **(options or {})}
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")
    if dst.suffix.lower() != ".wav":
        raise ValueError(f"convert_to_wav requires a .wav output path; got: {dst}")

    probed_sr, probed_channels = _probe_audio_shape(src)
    sample_rate = int(opts["sample_rate"] or probed_sr)
    channels = int(opts["channels"] or probed_channels)
    codec = str(opts["sample_fmt"])
    verbose = opts.get("verbose", True)

    if verbose:
        stage_header(_STAGE, src, dst, {"sample_rate": sample_rate, "channels": channels})

    tmp = dst.parent / (f".~{_STAGE}~" + dst.name)
    try:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(src),
            "-map",
            "0:a:0",
            "-vn",
            "-c:a",
            codec,
            "-ar",
            str(sample_rate),
            "-ac",
            str(channels),
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-y",
            str(tmp),
        ]

        log.debug("convert_to_wav command: %s", " ".join(cmd))

        with stage_timer(_STAGE, "converted"):
            result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed (exit {result.returncode}):\n{result.stderr.strip()}")

        tmp.rename(dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    return {
        "output_path": str(dst),
        "codec": codec,
        "sample_rate": sample_rate,
        "channels": channels,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Convert a media file's primary audio stream to WAV")
    parser.add_argument("--input", required=True, help="Input media file")
    parser.add_argument("--output", required=True, help="Output WAV file")
    parser.add_argument("--options", default=None, help="JSON string of options")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    opts = json.loads(args.options) if args.options else None
    result = run(args.input, args.output, options=opts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
