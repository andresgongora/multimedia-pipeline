"""Stage: clean_recorded_voice — enhance recorded voice audio for clarity.

Runs a voice-cleaning tool on an audio file. Designed for lossless audio-only
workflows: input and output should be audio files (WAV, FLAC, M4A, etc.),
not video containers.

Current tool: "audio-filter" (Docker-based, uses DeepFilterNet + ffmpeg chain).
Targets: -14 LUFS, -1 dBTP, LRA 5-8 LU.

Inputs:
    input_path  — path to source audio file (audio only, not video)
    output_path — path for cleaned audio file

Options:
    tool        — cleaning tool to use (default: "audio-filter")
                  "audio-filter" = Docker-based DeepFilterNet + ffmpeg
    dfn_atten   — DeepFilterNet attenuation in dB, 0-100 (default: 20)
                  Higher = more aggressive noise removal

Returns:
    dict with keys: output_path, tool

Example usage:
    # As Python function
    from stages.clean_recorded_voice import run
    result = run("voice.wav", "voice_clean.wav")
    result = run("voice.wav", "voice_clean.wav", options={"dfn_atten": 30})

    # As CLI
    uv run -m stages.clean_recorded_voice.run --input voice.wav --output voice_clean.wav
        uv run -m stages.clean_recorded_voice.run --input voice.wav --output voice_clean.wav \
            --options '{"dfn_atten": 30}'
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from pathlib import Path

from shared.output import stage_header, stage_timer

log = logging.getLogger(__name__)

_STAGE = "clean_recorded_voice"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "tool": "audio-filter",
    "dfn_atten": 20,
    "verbose": True,
}

_TOOLS_DIR = Path(__file__).resolve().parent / "tools"


# ---------------------------------------------------------------------------
# Tool runners
# ---------------------------------------------------------------------------


def _run_audio_filter(src: Path, dst: Path, opts: dict) -> None:
    """Run the audio-filter Docker tool."""
    run_sh = _TOOLS_DIR / "audio-filter" / "run.sh"
    if not run_sh.exists():
        raise FileNotFoundError(f"audio-filter tool not found: {run_sh}")

    # audio-filter mounts CWD as /data inside Docker.
    # If input and output are in different directories, copy input to
    # output dir, process there, then clean up the copy.
    src = src.resolve()
    dst = dst.resolve()

    temp_input = None
    if src.parent != dst.parent:
        temp_input = dst.parent / f".~clean_recorded_voice~{src.name}"
        shutil.copy2(src, temp_input)
        work_src = temp_input
    else:
        work_src = src

    work_dir = dst.parent
    cmd = [
        str(run_sh),
        work_src.name,
        dst.name,
        f"--dfn-atten-db={opts['dfn_atten']}",
    ]

    log.debug("Command: %s (cwd=%s)", " ".join(cmd), work_dir)

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)

    if temp_input and temp_input.exists():
        temp_input.unlink()

    if result.returncode != 0:
        raise RuntimeError(
            f"audio-filter failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}\n{result.stdout.strip()}"
        )


_TOOL_RUNNERS = {
    "audio-filter": _run_audio_filter,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Clean recorded voice audio.

    Raises:
        FileNotFoundError: if input does not exist or tool not found.
        FileExistsError:   if output already exists.
        ValueError:        if unknown tool specified.
        RuntimeError:      if tool execution fails.
    """
    opts = {**DEFAULTS, **(options or {})}
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    tool = opts["tool"]
    if tool not in _TOOL_RUNNERS:
        raise ValueError(f"Unknown tool '{tool}'. Choose from: {list(_TOOL_RUNNERS.keys())}")

    verbose = opts.get("verbose", True)
    if verbose:
        stage_header(_STAGE, src, dst, {"tool": tool, "dfn_atten": opts["dfn_atten"]})

    with stage_timer(_STAGE, dst.name):
        _TOOL_RUNNERS[tool](src, dst, opts)

    if not dst.exists():
        raise RuntimeError(f"Tool '{tool}' completed but output not found: {dst}")

    return {
        "output_path": str(dst),
        "tool": tool,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli():
    parser = argparse.ArgumentParser(description="Clean recorded voice audio")
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
