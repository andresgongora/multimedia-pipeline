"""Stage: add_metadata — embed metadata into a media file using ffmpeg (stream copy).

Writes standard fields (title, artist, album, etc.) and arbitrary custom fields
into any container supported by ffmpeg without re-encoding.

Custom fields used by this project (stored as uppercase ffmpeg metadata keys):
  - ORIGINAL_DURATION : original file duration in seconds before any processing
  - SCRUBBED          : seconds of content removed
  - AUDIO_FILTER      : description of audio processing applied

Inputs:
    input_path  — path to source media file (audio or video)
    output_path — path for tagged output file

Options:
    fields   — dict of metadata key→value pairs to write (default: {})
               Standard keys: title, artist, album, comment, date, genre, track
               Custom keys: any uppercase string (e.g. ORIGINAL_DURATION)
    preserve — whether to copy existing metadata from the source (default: True)
    verbose  — print progress (default: True)

Returns:
    dict with keys: output_path

Example usage:
    result = run("audio.m4a", "tagged.m4a", options={
        "fields": {
            "title": "My Podcast Episode",
            "artist": "Some Channel",
            "comment": "youtube:dQw4w9WgXcQ",
            "ORIGINAL_DURATION": "3600.00",
            "SCRUBBED": "42.50",
            "AUDIO_FILTER": "Podcast filter (EQ+compression+loudnorm)",
        }
    })

    # CLI
    uv run -m stages.add_metadata --input audio.m4a --output tagged.m4a \\
        --options '{"fields": {"title": "My Episode", "artist": "Me"}}'
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from shared.output import stage_header, stage_timer

_STAGE = "add_metadata"

DEFAULTS: dict = {
    "fields": {},
    "preserve": True,
    "verbose": True,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    verbose: bool = opts["verbose"]
    fields: dict = opts["fields"]
    preserve: bool = opts["preserve"]

    src = Path(input_path)
    dst = Path(output_path)

    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    if verbose:
        field_summary = ", ".join(fields.keys()) if fields else "(none)"
        stage_header(_STAGE, src, dst, {"fields": field_summary})

    metadata_args: list[str] = []
    for key, val in fields.items():
        metadata_args.extend(["-metadata", f"{key}={val}"])

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-c",
        "copy",
    ]
    if preserve:
        cmd += ["-map_metadata", "0"]
    else:
        cmd += ["-map_metadata", "-1"]
    cmd += metadata_args
    cmd.append(str(dst))

    with stage_timer(_STAGE, "embed metadata"):
        subprocess.run(cmd, capture_output=True, check=True)

    return {"output_path": str(dst)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Embed metadata into a media file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--options", default="{}", type=json.loads)
    args = parser.parse_args()
    result = run(args.input, args.output, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
