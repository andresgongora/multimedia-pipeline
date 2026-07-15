"""Shared ffprobe helpers for querying media file metadata.

Centralises all ffprobe calls to avoid code duplication across stages.
All functions return None or empty values on failure rather than raising,
allowing callers to handle missing data gracefully.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def get_duration(path: Path) -> float | None:
    """Return duration of *path* in seconds, or None on failure."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return None


def get_duration_strict(path: Path) -> float:
    """Return duration of *path* in seconds. Raises on failure."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def has_video_stream(path: Path) -> bool:
    """Return True if *path* contains at least one video stream."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "video"


def get_streams(path: Path) -> list[dict]:
    """Return list of stream dicts from ffprobe, or empty list on failure."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    try:
        return json.loads(result.stdout).get("streams", [])
    except (json.JSONDecodeError, KeyError):
        return []


def get_format(path: Path) -> dict:
    """Return format dict from ffprobe, or empty dict on failure."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout).get("format", {})
    except (json.JSONDecodeError, KeyError):
        return {}


def get_format_and_streams(path: Path) -> tuple[dict, list[dict]]:
    """Return (format_dict, streams_list) from ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}, []
    try:
        data = json.loads(result.stdout)
        return data.get("format", {}), data.get("streams", [])
    except (json.JSONDecodeError, KeyError):
        return {}, []


def get_tags(path: Path) -> dict[str, str]:
    """Return metadata tags (case-insensitive keys), checking format then streams."""
    fmt, streams = get_format_and_streams(path)
    tags = fmt.get("tags", {})
    # Opus/OGG store tags at stream level
    if not tags:
        for stream in streams:
            if stream.get("tags"):
                tags = stream["tags"]
                break
    # Normalise keys to lowercase
    return {k.lower(): v for k, v in tags.items()}


def get_audio_bitrate(path: Path) -> int | None:
    """Return audio bitrate in bits/second, or None if unavailable."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=bit_rate:format=bit_rate",
            "-select_streams",
            "a:0",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        stream_br = streams[0].get("bit_rate") if streams else None
        format_br = (data.get("format") or {}).get("bit_rate")
        raw = stream_br or format_br
        return int(raw) if raw else None
    except (json.JSONDecodeError, ValueError, IndexError):
        return None


def get_codec_names(path: Path) -> dict[str, str]:
    """Return {'video': codec_name, 'audio': codec_name} for streams in *path*."""
    codecs: dict[str, str] = {}
    for stream in get_streams(path):
        ctype = stream.get("codec_type", "")
        cname = stream.get("codec_name", "")
        if ctype in ("video", "audio") and cname and ctype not in codecs:
            codecs[ctype] = cname
    return codecs
