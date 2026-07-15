"""Stage: cut — remove time ranges from a media file using ffmpeg.

Two modes:

  "precise" (default) — Re-encodes using the same codecs as the input file.
                        Frame-accurate cuts regardless of keyframe positions.
                        Slower; always works.

  "fast"              — Stream copy via the ffmpeg concat demuxer. No re-encode,
                        no quality loss. Cut points are snapped to the nearest
                        video keyframe so cuts are only keyframe-accurate.
                        For audio-only files this is always frame-accurate
                        (audio has no keyframe concept).

Inputs:
    input_path  — path to source media file (audio or video)
    output_path — path for the cut output file
    remove      — list of [start, end] pairs (seconds) to remove
                  e.g. [[10.0, 30.5], [120.0, 135.0]]

Options:
    mode    — "precise" (default) | "fast"
    verbose — print progress (default: True)

Returns:
    {
      "output_path":   "...",
      "removed_count": 3,
      "mode":          "precise",
    }

Example usage:
    result = run("video.mp4", "cut.mp4", [[10.0, 30.0], [90.0, 95.0]])

    result = run("audio.m4a", "cut.m4a", [[30.0, 60.0]], options={"mode": "fast"})

    # CLI
    uv run -m stages.cut --input video.mp4 --output cut.mp4 \\
        --remove '[[10.0, 30.0], [90.0, 95.0]]'
    uv run -m stages.cut --input video.mp4 --output cut.mp4 \\
        --remove '[[10.0, 30.0]]' --options '{"mode": "fast"}'
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from shared.ffprobe import get_duration_strict, get_streams, has_video_stream
from shared.output import stage_header, stage_log, stage_timer

_STAGE = "cut"

DEFAULTS: dict = {
    "mode": "precise",
    "verbose": True,
}

# Maps ffprobe codec names → ffmpeg encoder names for same-codec re-encode
_ENCODER_MAP: dict[str, str] = {
    "h264": "libx264",
    "hevc": "libx265",
    "vp8": "libvpx",
    "vp9": "libvpx-vp9",
    "av1": "libaom-av1",
    "aac": "aac",
    "mp3": "libmp3lame",
    "opus": "libopus",
    "vorbis": "libvorbis",
    "flac": "flac",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    input_path: str,
    output_path: str,
    remove: list[list[float]] | list[tuple[float, float]],
    *,
    options: dict | None = None,
) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    verbose: bool = opts["verbose"]
    mode: str = opts["mode"]

    src = Path(input_path)
    dst = Path(output_path)

    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    remove_ranges: list[tuple[float, float]] = [tuple(r) for r in remove]  # type: ignore[misc]

    if not remove_ranges:
        if verbose:
            stage_log(_STAGE, "no ranges to remove — copying as passthrough")
        shutil.copy2(str(src), str(dst))
        return {"output_path": str(dst), "removed_count": 0, "mode": mode, "passthrough": True}

    if verbose:
        stage_header(_STAGE, src, dst, {"mode": mode, "ranges": len(remove_ranges)})

    reencode = mode == "precise"

    input_duration = _get_duration(src)

    with stage_timer(_STAGE, "cut"):
        _remove_segments(src, remove_ranges, dst, reencode)

    output_duration = _get_duration(dst)
    actual_cut = input_duration - output_duration

    if verbose:
        stage_log(_STAGE, f"[dim]{len(remove_ranges)} segment(s), {actual_cut:.1f}s actually cut[/]")

    return {
        "output_path": str(dst),
        "removed_count": len(remove_ranges),
        "mode": mode,
        "actual_cut_seconds": actual_cut,
    }


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def _remove_segments(
    src: Path,
    skip_ranges: list[tuple[float, float]],
    dst: Path,
    reencode: bool,
) -> None:
    duration = _get_duration(src)
    merged = _merge(skip_ranges)
    keep = _invert(merged, duration)

    if not keep:
        raise ValueError("All content would be removed — nothing to keep.")

    concat_content = _build_concat_list(src, keep)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, dir=str(dst.parent), prefix=".~cut_concat~"
    ) as f:
        f.write(concat_content)
        concat_file = f.name

    try:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
        ]
        if _has_video(src):
            cmd += ["-map", "0:v"]
        cmd += ["-map", "0:a"]
        cmd += ["-map_metadata", "-1", "-map_chapters", "-1"]

        if reencode:
            cmd += _same_codec_flags(src)
        else:
            cmd += ["-c", "copy"]

        cmd += ["-y", str(dst)]
        subprocess.run(cmd, stdin=subprocess.DEVNULL, check=True)
    finally:
        Path(concat_file).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Codec detection
# ---------------------------------------------------------------------------


def _same_codec_flags(src: Path) -> list[str]:
    """Return ffmpeg -c:v / -c:a flags that re-encode using the same codecs as *src*."""
    streams = get_streams(src)
    flags: list[str] = []
    for stream in streams:
        codec = stream.get("codec_name", "")
        ctype = stream.get("codec_type", "")
        encoder = _ENCODER_MAP.get(codec, codec)
        if ctype == "video":
            flags += ["-c:v", encoder]
        elif ctype == "audio":
            flags += ["-c:a", encoder]
    return flags


# ---------------------------------------------------------------------------
# Segment math helpers
# ---------------------------------------------------------------------------


def _get_duration(path: Path) -> float:
    return get_duration_strict(path)


def _has_video(path: Path) -> bool:
    return has_video_stream(path)


def _snap_to_keyframe(src: Path, t: float) -> float:
    """Return the first video keyframe at or after *t* seconds."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-select_streams",
            "v:0",
            "-read_intervals",
            f"{t:.6f}%+10",
            "-skip_frame",
            "nokey",
            "-show_entries",
            "frame=pts_time",
            "-of",
            "csv=p=0",
            str(src),
        ],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            try:
                return float(line)
            except ValueError:
                pass
    return t


def _merge(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not ranges:
        return []
    segs = sorted(ranges)
    merged: list[list[float]] = [list(segs[0])]
    for s, e in segs[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def _invert(remove: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for s, e in sorted(remove):
        if cursor < s:
            keep.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        keep.append((cursor, duration))
    return keep


def _build_concat_list(src: Path, keep: list[tuple[float, float]]) -> str:
    abs_path = src.resolve()
    escaped = str(abs_path).replace("'", "'\\''")
    lines = ["ffconcat version 1.0"]
    for i, (start, end) in enumerate(keep):
        snapped = start if (i == 0 and start == 0.0) else _snap_to_keyframe(src, start)
        lines.append(f"file '{escaped}'")
        lines.append(f"inpoint {snapped:.6f}")
        lines.append(f"outpoint {end:.6f}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Cut time ranges from a media file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--remove",
        required=True,
        type=json.loads,
        help="JSON list of [start, end] pairs, e.g. [[10.0, 30.0]]",
    )
    parser.add_argument("--options", default="{}", type=json.loads)
    args = parser.parse_args()
    result = run(args.input, args.output, args.remove, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
