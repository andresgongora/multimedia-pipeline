"""Stage: remove_silences — remove silent segments from media files.

Detects and cuts silent portions from audio or video files. The result is a
shorter file with silences removed.

Methods:
    "auto-editor"    — (default) Uses auto-editor via Docker to detect and cut
                       silences in a single pass. Good quality, handles both
                        audio and video. See stages/remove_silences/tools/silence-remover/.

    "detect-and-cut" — (not yet implemented) Two-phase approach: first detect
                       silence intervals via a find_silences stage, then cut
                       them via a cut_video stage. More composable — allows
                       inspecting/adjusting detected silences before cutting.
                       Planned for future implementation.

Inputs:
    input_path  — path to source media file (audio or video)
    output_path — path for output file with silences removed

Options:
    method      — removal method (default: "auto-editor")
    threshold   — silence threshold, linear amplitude 0-1 (default: 0.03 ≈ -30 dB)
    margin      — padding kept on each side of a cut (default: "0.25sec")
    normalize   — pre-normalize audio loudness before silence detection
                  (default: true). Prevents over-cutting on quiet recordings.
                  Uses ffmpeg loudnorm; video stream is copied losslessly.
    normalize_target — LUFS target for loudnorm (default: -16)

Returns:
    dict with keys: output_path, method

Example usage:
    # As Python function
    from stages.remove_silences import run
    result = run("recording.mp4", "recording_trimmed.mp4")
    result = run("recording.mp4", "recording_trimmed.mp4",
                 options={"threshold": 0.02, "margin": "0.3sec"})

    # As CLI
    uv run -m stages.remove_silences.run --input recording.mp4 --output trimmed.mp4
        uv run -m stages.remove_silences.run --input in.mp4 --output out.mp4 \
            --options '{"threshold": 0.02}'
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from shared.ffprobe import has_video_stream
from shared.output import stage_header, stage_log, stage_timer

log = logging.getLogger(__name__)

_STAGE = "remove_silences"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "method": "auto-editor",
    "threshold": 0.03,  # linear amplitude ≈ -30 dB
    "margin": "0.25sec",
    "normalize": True,  # pre-normalize audio for reliable silence detection
    "normalize_target": -16,  # LUFS target for loudnorm
    "verbose": True,
}

_TOOLS_DIR = Path(__file__).resolve().parent / "tools"

_ROTATION_RE = re.compile(r"ROTATION=(-?\d+)")


# ---------------------------------------------------------------------------
# Rotation metadata restoration
# ---------------------------------------------------------------------------


def _restore_rotation(video: Path, stderr_output: str) -> None:
    """Re-apply rotation metadata to video if auto-editor stripped it.

    Parses ROTATION=<deg> from the tool's stderr and uses the host ffmpeg
    -display_rotation flag to set the display matrix.
    """
    match = _ROTATION_RE.search(stderr_output)
    if not match:
        return

    rotation = match.group(1)
    tmp = video.parent / f".~rotation_fix~{video.name}"

    # -display_rotation is an input option in ffmpeg ≥5.x: it overrides the
    # display matrix read from the input, which then gets written to output.
    cmd = [
        "ffmpeg",
        "-y",
        "-display_rotation:v:0",
        rotation,
        "-i",
        str(video),
        "-c",
        "copy",
        str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and tmp.exists():
        tmp.replace(video)
        stage_log(_STAGE, f"[dim]restored rotation: {rotation}°[/]")
        return

    # Fallback: -metadata:s:v rotate (older ffmpeg, H.264/MOV)
    if tmp.exists():
        tmp.unlink()
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video),
        "-c",
        "copy",
        "-metadata:s:v",
        f"rotate={rotation}",
        str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0 and tmp.exists():
        tmp.replace(video)
        stage_log(_STAGE, f"[dim]restored rotation (tag): {rotation}°[/]")
        return

    if tmp.exists():
        tmp.unlink()
    log.warning("Could not restore rotation metadata (%s°)", rotation)


def _has_video_stream(path: Path) -> bool:
    """Return True if *path* contains at least one video stream."""
    return has_video_stream(path)


# ---------------------------------------------------------------------------
# Audio normalization (extract → normalize → remux)
# ---------------------------------------------------------------------------


def _normalize_audio_in_video(src: Path, dst: Path, opts: dict) -> None:
    """Normalize audio loudness in a media file.

    For video files: extract audio → normalize → remux with original video (stream copy).
    For audio-only files: extract to WAV → normalize → write normalized WAV to dst.
    """
    from stages.extract_audio import run as extract_audio
    from stages.normalize_audio import run as normalize_audio
    from stages.remux_audio import run as remux_audio

    target_lufs = opts.get("normalize_target", -16)
    stem = src.stem

    audio_only = not _has_video_stream(src)

    temp_audio = dst.parent / f".~remove_silences_audio~{stem}.wav"
    temp_norm = dst.parent / f".~remove_silences_normaudio~{stem}.wav"

    try:
        # 1. Extract audio (silent — sub-stage)
        extract_audio(
            str(src),
            str(temp_audio),
            options={"codec": "lossless", "verbose": False},
        )

        # 2. Normalize audio (silent — sub-stage)
        normalize_audio(
            str(temp_audio),
            str(temp_norm),
            options={"target_lufs": target_lufs, "verbose": False},
        )

        # Clean up extracted audio early
        if temp_audio.exists():
            temp_audio.unlink()

        if audio_only:
            # For audio-only files, the normalized WAV is the final output
            temp_norm.rename(dst)
        else:
            # 3. Remux: original video stream + normalized audio (silent — sub-stage)
            remux_audio(
                str(src),
                str(temp_norm),
                str(dst),
                options={"verbose": False},
            )
    finally:
        for tmp in (temp_audio, temp_norm):
            if tmp.exists():
                tmp.unlink()


# ---------------------------------------------------------------------------
# Method runners
# ---------------------------------------------------------------------------


def _run_auto_editor(src: Path, dst: Path, opts: dict) -> None:
    """Run the silence-remover Docker tool (auto-editor)."""
    run_sh = _TOOLS_DIR / "silence-remover" / "run.sh"
    if not run_sh.exists():
        raise FileNotFoundError(f"silence-remover tool not found: {run_sh}")

    src = src.resolve()
    dst = dst.resolve()

    # Docker mounts CWD as /data. If input and output are in different
    # directories, copy input to output dir so both are under one mount.
    temp_input = None
    if src.parent != dst.parent:
        temp_input = dst.parent / f".~remove_silences~{src.name}"
        shutil.copy2(src, temp_input)
        work_src = temp_input
    else:
        work_src = src

    work_dir = dst.parent
    cmd = [
        str(run_sh),
        work_src.name,
        dst.name,
        str(opts["threshold"]),
        str(opts["margin"]),
    ]

    log.debug("Command: %s (cwd=%s)", " ".join(cmd), work_dir)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir)
    finally:
        if temp_input and temp_input.exists():
            temp_input.unlink()

    if result.returncode != 0:
        raise RuntimeError(
            f"silence-remover failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}\n{result.stdout.strip()}"
        )

    # auto-editor re-encodes video but does not auto-rotate pixels, yet strips
    # rotation metadata. The entrypoint prints ROTATION=<deg> to stderr if the
    # original had rotation. Re-apply it using the host ffmpeg.
    _restore_rotation(dst, result.stderr)


def _run_detect_and_cut(src: Path, dst: Path, opts: dict) -> None:
    """Two-phase silence removal: detect intervals, then cut.

    Not yet implemented. Will compose a find_silences stage (to detect
    silence intervals) with a cut_video stage (to remove them).
    This allows inspecting or adjusting detected silences before cutting.
    """
    raise NotImplementedError(
        "The 'detect-and-cut' method is not yet implemented. "
        "It will use find_silences + cut_video stages when available. "
        "Use 'auto-editor' for now."
    )


_METHOD_RUNNERS = {
    "auto-editor": _run_auto_editor,
    "detect-and-cut": _run_detect_and_cut,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Remove silences from a media file.

    Raises:
        FileNotFoundError: if input does not exist or tool not found.
        FileExistsError:   if output already exists.
        ValueError:        if unknown method specified.
        RuntimeError:      if tool execution fails.
        NotImplementedError: if method not yet available.
    """
    opts = {**DEFAULTS, **(options or {})}
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    method = opts["method"]
    if method not in _METHOD_RUNNERS:
        raise ValueError(f"Unknown method '{method}'. Choose from: {list(_METHOD_RUNNERS.keys())}")

    normalize = opts.get("normalize", True)
    verbose = opts.get("verbose", True)
    if verbose:
        stage_header(_STAGE, src, dst, {"method": method, "normalize": normalize})

    # Optionally pre-normalize audio so silence detection works on quiet input
    temp_normalized = None
    actual_src = src
    if normalize:
        temp_normalized = dst.parent / f".~remove_silences_norm~{src.name}"
        if verbose:
            stage_log(_STAGE, "[dim]pre-normalizing audio…[/]")
        _normalize_audio_in_video(src, temp_normalized, opts)
        actual_src = temp_normalized

    try:
        with stage_timer(_STAGE, "silences removed"):
            _METHOD_RUNNERS[method](actual_src, dst, opts)
    finally:
        if temp_normalized and temp_normalized.exists():
            temp_normalized.unlink()

    if not dst.exists():
        raise RuntimeError(f"Method '{method}' completed but output not found: {dst}")

    return {
        "output_path": str(dst),
        "method": method,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli():
    parser = argparse.ArgumentParser(description="Remove silences from media")
    parser.add_argument("--input", required=True, help="Input media file")
    parser.add_argument("--output", required=True, help="Output media file")
    parser.add_argument("--options", default=None, help="JSON string of options")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    opts = json.loads(args.options) if args.options else None
    result = run(args.input, args.output, options=opts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
