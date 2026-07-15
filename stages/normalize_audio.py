"""Stage: normalize_audio — loudness-normalize an audio file.

Applies EBU R128 loudness normalization (ffmpeg loudnorm filter) to an audio
file. Output is uncompressed PCM — no lossy encoding.

Inputs:
    input_path  — path to source audio file
    output_path — path for normalized audio file

Options:
    target_lufs — integrated loudness target in LUFS (default: -16)
    target_tp   — true peak ceiling in dBTP (default: -1)
    target_lra  — loudness range target in LU (default: 11)

Returns:
    dict with keys: output_path

Example usage:
    from stages.normalize_audio import run
    result = run("voice.wav", "voice_norm.wav")
    result = run("voice.wav", "voice_norm.wav", options={"target_lufs": -14})

    # CLI
    uv run -m stages.normalize_audio --input voice.wav --output voice_norm.wav
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path

from shared.output import stage_header, stage_timer

log = logging.getLogger(__name__)

_STAGE = "normalize_audio"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "target_lufs": -16,
    "target_tp": -1,
    "target_lra": 11,
    "verbose": True,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Normalize audio loudness using ffmpeg loudnorm.

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

    lufs = opts["target_lufs"]
    tp = opts["target_tp"]
    lra = opts["target_lra"]
    verbose = opts.get("verbose", True)

    if verbose:
        stage_header(_STAGE, src, dst, {"target_lufs": lufs})

    # Probe input sample rate so we can preserve it.
    # loudnorm internally upsamples to 192 kHz for EBU R128 analysis; without
    # an explicit -ar ffmpeg writes the output at 192 kHz, which causes
    # downstream stages to interpret audio at the wrong speed/pitch.
    from shared.ffprobe import get_streams as _get_streams
    _streams = _get_streams(src)
    _sr = next(
        (int(s["sample_rate"]) for s in _streams if s.get("codec_type") == "audio" and s.get("sample_rate")),
        48000,
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-af",
        f"loudnorm=I={lufs}:TP={tp}:LRA={lra}",
        "-c:a",
        "pcm_s16le",
        "-ar",
        str(_sr),
        str(dst),
    ]

    log.debug("Normalize command: %s", " ".join(cmd))

    with stage_timer(_STAGE) as ctx:
        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg loudnorm failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )

    if not dst.exists():
        raise RuntimeError(f"loudnorm completed but output not found: {dst}")

    return {"output_path": str(dst)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli():
    parser = argparse.ArgumentParser(description="Normalize audio loudness")
    parser.add_argument("--input", required=True, help="Input audio file")
    parser.add_argument("--output", required=True, help="Output audio file")
    parser.add_argument("--options", default=None, help="JSON string of options")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    opts = json.loads(args.options) if args.options else None
    result = run(args.input, args.output, options=opts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
