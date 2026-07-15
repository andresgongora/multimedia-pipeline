"""Stage: extract_and_clean_voice — extract lossless audio from video, then clean.

Compound stage composing extract_audio + clean_recorded_voice. Extracts audio
as lossless WAV (duration-matched to video container), runs voice cleaning,
and saves result to specified output path.

Intermediate temp files use the .~<stage>~ convention and are cleaned up
after processing.

Inputs:
    input_path  — path to source video file
    output_path — path for cleaned audio file (WAV recommended)

Options:
    extract     — options dict passed to extract_audio (default: {"codec": "lossless"})
    clean       — options dict passed to clean_recorded_voice (default: {})

Returns:
    dict with keys: output_path, extract_result, clean_result

Example usage:
    from stages.extract_and_clean_voice import run
    result = run("video.mp4", "cleaned.wav")
    result = run("video.mp4", "cleaned.wav", options={"clean": {"dfn_atten": 30}})

    # CLI
    uv run -m stages.extract_and_clean_voice --input video.mp4 --output cleaned.wav
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

from stages.clean_recorded_voice import run as clean_voice
from stages.extract_audio import run as extract_audio

log = logging.getLogger(__name__)

_STAGE = "extract_and_clean_voice"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "extract": {"codec": "lossless"},
    "clean": {},
    "verbose": True,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Extract lossless audio from video and clean recorded voice.

    Raises:
        FileNotFoundError: if input does not exist.
        FileExistsError:   if output already exists.
        RuntimeError:      if any stage fails.
    """
    opts = {**DEFAULTS, **(options or {})}
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    # Temp files live next to output (same dir required by audio-filter)
    stem = dst.stem
    ext = dst.suffix or ".wav"
    temp_extracted = dst.parent / f".~extract_audio~{stem}{ext}"
    temp_cleaned = dst.parent / f".~clean_recorded_voice~{stem}{ext}"

    try:
        # Stage 1: extract lossless audio
        extract_result = extract_audio(str(src), str(temp_extracted), options=opts["extract"])

        # Stage 2: clean voice
        clean_result = clean_voice(str(temp_extracted), str(temp_cleaned), options=opts["clean"])

        # Move final result to output path
        shutil.move(str(temp_cleaned), str(dst))

        return {
            "output_path": str(dst),
            "extract_result": extract_result,
            "clean_result": clean_result,
        }

    finally:
        # Clean up temp files
        for tmp in (temp_extracted, temp_cleaned):
            if tmp.exists():
                tmp.unlink()
                log.debug("Cleaned temp: %s", tmp)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli():
    parser = argparse.ArgumentParser(description="Extract and clean voice from video")
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
