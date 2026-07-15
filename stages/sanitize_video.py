"""Stage: sanitize_video — prepare video for downstream editing stages.

Sanitizes camera/video inputs before later processing.

Default behavior:
    - probes video stream metadata
    - warns if input looks like variable framerate (VFR)
    - copies input to output unchanged

Optional fixes:
    - rotate pixels in 90° increments (90 / 180 / 270)
    - transcode to constant framerate (CFR) at explicit target fps

Inputs:
    input_path  — path to source video file
    output_path — path for sanitized video file

Options:
    warn_variable_framerate — warn when avg fps differs from nominal fps
                              (default: true)
    fix_framerate           — transcode to CFR using target_fps (default: false)
    target_fps              — explicit fps for CFR output, e.g. 30 or 60
                              (default: None)
    rotate                  — pixel rotation in degrees: 0, 90, 180, 270
                              (default: 0)
    video_codec             — output video encoder when transcoding.
                              Default: "libx264". Use "same" to try matching
                              input codec when known.
    audio_codec             — output audio codec when transcoding.
                              Default: "copy"
    crf                     — quality factor for x264/x265 encodes
                              (default: 18)
    preset                  — speed/quality preset for x264/x265
                              (default: "medium")
    pixel_format            — output pixel format when transcoding
                              (default: "yuv420p")

Returns:
    dict with keys: output_path, passthrough, variable_framerate_detected,
    avg_fps, nominal_fps, rotate, fixed_framerate

Example usage:
    from stages.sanitize_video import run
    result = run("input.mp4", "sanitized.mp4")
    result = run(
        "input.mp4",
        "sanitized.mp4",
        options={"rotate": 90, "fix_framerate": True, "target_fps": 30},
    )

    # CLI
    uv run -m stages.sanitize_video --input input.mp4 --output sanitized.mp4
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from shared.ffprobe import get_streams, has_video_stream
from shared.output import stage_header, stage_log, stage_timer

_STAGE = "sanitize_video"

DEFAULTS: dict = {
    "warn_variable_framerate": True,
    "fix_framerate": False,
    "target_fps": None,
    "rotate": 0,
    "video_codec": "libx264",
    "audio_codec": "copy",
    "crf": 18,
    "preset": "medium",
    "pixel_format": "yuv420p",
    "verbose": True,
}

_VALID_ROTATIONS = {0, 90, 180, 270}
_ENCODER_MAP: dict[str, str] = {
    "h264": "libx264",
    "hevc": "libx265",
    "vp8": "libvpx",
    "vp9": "libvpx-vp9",
    "av1": "libaom-av1",
    "mpeg4": "mpeg4",
}


def _parse_rate(value: str | None) -> float | None:
    """Parse ffprobe frame-rate string like 30000/1001 into float."""
    if not value or value in ("0/0", "N/A"):
        return None
    try:
        rate = Fraction(value)
    except (ValueError, ZeroDivisionError):
        return None
    return float(rate) if rate else None


def _get_video_stream(path: Path) -> dict:
    """Return first video stream dict, or empty dict if missing."""
    return next((s for s in get_streams(path) if s.get("codec_type") == "video"), {})


def _is_likely_variable_framerate(stream: dict, tolerance: float = 0.01) -> bool:
    """Return True when avg fps differs materially from nominal fps."""
    avg_fps = _parse_rate(stream.get("avg_frame_rate"))
    nominal_fps = _parse_rate(stream.get("r_frame_rate"))
    if avg_fps is None or nominal_fps is None:
        return False
    if avg_fps == 0 or nominal_fps == 0:
        return False
    return abs(avg_fps - nominal_fps) > tolerance


def _probe_video(path: Path) -> dict:
    """Return sanitized metadata summary for first video stream."""
    stream = _get_video_stream(path)
    return {
        "codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "avg_fps": _parse_rate(stream.get("avg_frame_rate")),
        "nominal_fps": _parse_rate(stream.get("r_frame_rate")),
        "likely_vfr": _is_likely_variable_framerate(stream),
    }


def _format_fps(value: float | None) -> str:
    """Format fps value for logs."""
    return "?" if value is None else f"{value:.3f}".rstrip("0").rstrip(".")


def _build_filter_chain(rotate: int, fix_framerate: bool, target_fps: float | int | None) -> str:
    """Build ffmpeg video filter chain for requested transforms."""
    filters: list[str] = []
    if rotate == 90:
        filters.append("transpose=1")
    elif rotate == 180:
        filters.append("transpose=1,transpose=1")
    elif rotate == 270:
        filters.append("transpose=2")

    if fix_framerate and target_fps is not None:
        filters.append(f"fps={target_fps}")

    return ",".join(filters)


def _resolve_video_encoder(requested: str, input_codec: str | None) -> str:
    """Resolve output encoder name."""
    if requested == "same":
        return _ENCODER_MAP.get(input_codec or "", "libx264")
    return requested


def _transcode(src: Path, dst: Path, opts: dict, meta: dict) -> None:
    """Transcode video with requested sanitize operations."""
    rotate = int(opts["rotate"])
    filter_chain = _build_filter_chain(rotate, opts["fix_framerate"], opts.get("target_fps"))
    encoder = _resolve_video_encoder(str(opts["video_codec"]), meta.get("codec"))

    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if filter_chain:
        cmd += ["-vf", filter_chain]
    if opts["fix_framerate"]:
        cmd += ["-fps_mode:v:0", "cfr"]

    cmd += ["-c:v", encoder]
    if encoder in ("libx264", "libx265"):
        cmd += [
            "-crf",
            str(opts["crf"]),
            "-preset",
            str(opts["preset"]),
            "-pix_fmt",
            str(opts["pixel_format"]),
        ]

    audio_codec = str(opts["audio_codec"])
    cmd += ["-c:a", audio_codec]
    if rotate:
        cmd += ["-metadata:s:v:0", "rotate=0"]
    cmd.append(str(dst))

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg sanitize failed (exit {result.returncode}):\n{result.stderr.strip()}")


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Sanitize video file for downstream editing/processing stages."""
    opts = {**DEFAULTS, **(options or {})}
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")
    if not has_video_stream(src):
        raise ValueError(f"Input has no video stream: {src}")

    rotate = int(opts.get("rotate", 0))
    if rotate not in _VALID_ROTATIONS:
        raise ValueError(f"Invalid rotate={rotate}. Choose from: {sorted(_VALID_ROTATIONS)}")

    fix_framerate = bool(opts.get("fix_framerate", False))
    target_fps = opts.get("target_fps")
    if fix_framerate and not target_fps:
        raise ValueError("target_fps required when fix_framerate=true")

    verbose = bool(opts.get("verbose", True))
    meta = _probe_video(src)
    likely_vfr = bool(meta["likely_vfr"])

    if verbose:
        config = {
            "rotate": rotate,
            "fix_framerate": fix_framerate,
        }
        if fix_framerate:
            config["target_fps"] = target_fps
        stage_header(_STAGE, src, dst, config)

    if likely_vfr and opts.get("warn_variable_framerate", True):
        stage_log(
            _STAGE,
            "[yellow]warning[/] likely variable framerate "
            f"(avg={_format_fps(meta['avg_fps'])} fps, nominal={_format_fps(meta['nominal_fps'])} fps)",
        )

    passthrough = not rotate and not fix_framerate
    if passthrough:
        with stage_timer(_STAGE, "copied as passthrough"):
            shutil.copy2(src, dst)
    else:
        with stage_timer(_STAGE, "sanitized"):
            _transcode(src, dst, opts, meta)

    if not dst.exists():
        raise RuntimeError(f"sanitize completed but output not found: {dst}")

    return {
        "output_path": str(dst),
        "passthrough": passthrough,
        "variable_framerate_detected": likely_vfr,
        "avg_fps": meta["avg_fps"],
        "nominal_fps": meta["nominal_fps"],
        "rotate": rotate,
        "fixed_framerate": fix_framerate,
        "target_fps": target_fps,
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Sanitize video for downstream processing")
    parser.add_argument("--input", required=True, help="Input video file")
    parser.add_argument("--output", required=True, help="Output video file")
    parser.add_argument("--options", default=None, help="JSON string of options")
    args = parser.parse_args()

    opts = json.loads(args.options) if args.options else None
    result = run(args.input, args.output, options=opts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
