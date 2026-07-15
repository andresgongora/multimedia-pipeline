"""Stage: remux_audio — replace audio track in a video with a different audio file.

Copies the video stream bit-for-bit and replaces the audio with the provided
audio file. No re-encoding of video. Audio is encoded as PCM s16le by default
(lossless) or can be stream-copied if formats are compatible.

Inputs:
    input_path  — path to source video file
    audio_path  — path to replacement audio file
    output_path — path for output video file

Options:
    audio_codec — "pcm_s16le" (default, lossless), "copy" (stream copy), or
                  any ffmpeg audio codec name
    verbose     — print progress (default: true)

Returns:
    dict with keys: output_path, audio_codec

Example usage:
    from stages.remux_audio import run
    result = run("video.mp4", "new_audio.wav", "video_remuxed.mp4")
    result = run("video.mp4", "audio.aac", "out.mp4", options={"audio_codec": "copy"})

    # CLI
    uv run -m stages.remux_audio --input video.mp4 --audio new_audio.wav --output out.mp4
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path

from shared.output import stage_header, stage_timer

log = logging.getLogger(__name__)

_STAGE = "remux_audio"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "audio_codec": "pcm_s16le",
    "verbose": True,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(
    input_path: str,
    audio_path: str,
    output_path: str,
    *,
    options: dict | None = None,
) -> dict:
    """Replace the audio track in a video file.

    Raises:
        FileNotFoundError: if input or audio file does not exist.
        FileExistsError:   if output already exists.
        RuntimeError:      if ffmpeg fails.
    """
    opts = {**DEFAULTS, **(options or {})}
    src = Path(input_path)
    audio = Path(audio_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Video input not found: {src}")
    if not audio.exists():
        raise FileNotFoundError(f"Audio input not found: {audio}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    audio_codec = opts["audio_codec"]
    verbose = opts.get("verbose", True)

    if verbose:
        stage_header(_STAGE, src, dst, {"audio": audio.name, "codec": audio_codec})

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-i",
        str(audio),
        "-c:v",
        "copy",
        "-c:a",
        audio_codec,
        "-map",
        "0:v",
        "-map",
        "1:a",
        str(dst),
    ]

    log.debug("Remux command: %s", " ".join(cmd))

    with stage_timer(_STAGE, dst.name):
        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg remux failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    if not dst.exists():
        raise RuntimeError(f"Remux completed but output not found: {dst}")

    return {
        "output_path": str(dst),
        "audio_codec": audio_codec,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli():
    parser = argparse.ArgumentParser(description="Replace audio track in a video file")
    parser.add_argument("--input", required=True, help="Input video file")
    parser.add_argument("--audio", required=True, help="Replacement audio file")
    parser.add_argument("--output", required=True, help="Output video file")
    parser.add_argument("--options", default=None, help="JSON string of options")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    opts = json.loads(args.options) if args.options else None
    result = run(args.input, args.audio, args.output, options=opts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
