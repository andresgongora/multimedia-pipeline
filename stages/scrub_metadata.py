"""Stage: scrub_metadata — strip privacy-sensitive metadata from a media file.

Removes as much metadata as possible (EXIF, GPS, camera info, dates, encoder
strings, etc.) while keeping the media streams intact. Uses ffmpeg stream copy
with -map_metadata -1, which drops the global metadata container entirely.

What gets removed (depending on container):
  - Camera/device info (make, model, software)
  - Recording date/time
  - GPS coordinates
  - Encoder/muxer strings
  - Comment, description, copyright fields
  - Any other global metadata tags

What is NOT removed:
  - In-stream codec parameters (required for playback)
  - Chapter markers (can be kept or stripped via option)

Inputs:
    input_path  — path to source media file (audio or video)
    output_path — path for scrubbed output file

Options:
    strip_chapters — also strip chapter metadata (default: False)
    verbose        — print progress (default: True)

Returns:
    dict with keys: output_path

Example usage:
    result = run("raw_recording.mp4", "clean.mp4")

    result = run("raw_recording.mp4", "clean.mp4", options={"strip_chapters": True})

    # CLI
    uv run -m stages.scrub_metadata --input raw.mp4 --output clean.mp4
    uv run -m stages.scrub_metadata --input raw.mp4 --output clean.mp4 \\
        --options '{"strip_chapters": true}'
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from shared.output import stage_header, stage_timer

_STAGE = "scrub_metadata"

DEFAULTS: dict = {
    "strip_chapters": False,
    "verbose": True,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    verbose: bool = opts["verbose"]
    strip_chapters: bool = opts["strip_chapters"]

    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    if verbose:
        stage_header(_STAGE, src, dst, {"strip_chapters": strip_chapters})

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-c",
        "copy",
        "-map_metadata",
        "-1",  # drop all global metadata
    ]

    if not strip_chapters:
        # Re-attach chapter info only (chapters are separate from global metadata)
        cmd += ["-map_chapters", "0"]
    else:
        cmd += ["-map_chapters", "-1"]

    cmd.append(str(dst))

    with stage_timer(_STAGE, "scrub metadata"):
        subprocess.run(cmd, capture_output=True, check=True)

    return {"output_path": str(dst)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Strip metadata from a media file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--options", default="{}", type=json.loads)
    args = parser.parse_args()
    result = run(args.input, args.output, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
