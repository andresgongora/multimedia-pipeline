"""Stage: identify_youtube_media — find the YouTube video matching a media file.

Tries to identify the YouTube source of a local media file using, in order:

  1. YouTube video ID embedded in the filename (bracketed [ID], URL form, or
     bare 11-char token) — exits immediately on hit.
  2. YouTube ID found in embedded comment tag ("youtube:ID" or full URL form)
     — exits immediately on hit.
  3. yt-dlp title search using embedded title/artist metadata tags as query
     (if search_fallback is enabled) — exits immediately if duration matches.
  4. yt-dlp title search using the filename stem as query (if search_fallback
     is enabled) — exits immediately if duration matches.

The stage stops as soon as any step succeeds. Steps 3 and 4 are both tried
unless they would produce the same query string (deduplication).

Duration matching uses a configurable tolerance (default ±5 s). When
ORIGINAL_DURATION is present in file metadata, that value is used for
comparison instead of the current (possibly trimmed) file duration.

Inputs:
    input_path — path to the media file to identify

Options:
    search_fallback     — fall back to yt-dlp title search when no ID in filename
                          (default: True)
    duration_tolerance  — seconds of acceptable mismatch between YouTube duration
                          and local duration (default: 5.0)
    verbose             — print progress (default: True)

Returns (identified):
    {
      "identified":        True,
      "video_id":          "dQw4w9WgXcQ",
      "url":               "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "title":             "...",
      "channel":           "...",
      "youtube_duration":  212.0,        # seconds as reported by YouTube
      "description":       "...",        # video description text
      "duration_matched":  True | False | None,
      "method":            "filename" | "metadata_field" | "search_metadata" | "search_filename",
    }

Returns (not identified):
    {
      "identified": False,
      "reason":     "...",
    }

Example usage:
    result = run("Rick Astley - Never Gonna Give You Up [dQw4w9WgXcQ].m4a")

    result = run("trimmed_podcast.m4a", options={"search_fallback": False})

    # CLI
    uv run -m stages.identify_youtube_media --input "video [dQw4w9WgXcQ].mp4"
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from shared.ffprobe import get_duration, get_tags
from shared.output import stage_header, stage_log, stage_timer

_STAGE = "identify_youtube_media"

DEFAULTS: dict = {
    "search_fallback": True,
    "duration_tolerance": 5.0,
    "verbose": True,
}

# ── ID extraction patterns ────────────────────────────────────────────────────

_BRACKETED_RE = re.compile(r"\[([A-Za-z0-9_-]{11})\]")
_URL_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")
_BARE_RE = re.compile(r"\b([A-Za-z0-9_-]{11})\b")
_PAREN_RE = re.compile(r"\([^)]*\)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(input_path: str, *, options: dict | None = None) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    verbose: bool = opts["verbose"]
    search_fallback: bool = opts["search_fallback"]
    tolerance: float = float(opts["duration_tolerance"])

    src = Path(input_path)

    if verbose:
        stage_header(_STAGE, src, config={"search_fallback": search_fallback})

    # Read embedded metadata once — used by multiple steps below
    embedded_id, original_duration, tag_title, tag_artist = _read_embedded_metadata(src)

    # Prefer ORIGINAL_DURATION for duration comparison (file may be trimmed)
    local_dur = _get_local_duration(src)
    compare_dur = original_duration if original_duration is not None else local_dur

    def _resolve(video_id: str, method: str) -> dict:
        with stage_timer(_STAGE, f"fetch info for {video_id}"):
            info = _fetch_video_info(video_id)
        if info is None:
            return {"identified": False, "reason": f"yt-dlp could not fetch info for {video_id}"}
        matched = _duration_matches(info["youtube_duration"], compare_dur, tolerance)
        return {"identified": True, "method": method, "duration_matched": matched, **info}

    def _try_search(query: str, method: str) -> dict | None:
        """Run yt-dlp search; return result dict on duration match, None otherwise."""
        if verbose:
            stage_log(_STAGE, f"searching ({method}): {query!r}")
        with stage_timer(_STAGE, f"search ({method})"):
            result = _search_youtube(query)
        if result is None:
            return None
        matched = _duration_matches(result["youtube_duration"], compare_dur, tolerance)
        if matched is False:
            if verbose:
                stage_log(
                    _STAGE,
                    f"duration mismatch for {result['video_id']}: "
                    f"YT={result['youtube_duration']}s local={compare_dur}s",
                )
            return None
        return {"identified": True, "method": method, "duration_matched": matched, **result}

    # ── Step 1: YouTube ID in filename ────────────────────────────────────
    video_id = _extract_id_from_filename(src)
    if video_id:
        if verbose:
            stage_log(_STAGE, f"ID from filename: {video_id}")
        return _resolve(video_id, "filename")

    # ── Step 2: YouTube ID in embedded comment tag ────────────────────────
    if embedded_id:
        if verbose:
            stage_log(_STAGE, f"ID from embedded metadata: {embedded_id}")
        return _resolve(embedded_id, "metadata_field")

    # ── Steps 3 & 4: title search ─────────────────────────────────────────
    if not search_fallback:
        return {"identified": False, "reason": "no ID found and search_fallback is disabled"}

    query_metadata = _build_search_query_from_tags(tag_title, tag_artist)
    query_filename = _build_search_query(src)

    # Step 3: search by embedded title/artist tags
    if query_metadata:
        hit = _try_search(query_metadata, "search_metadata")
        if hit:
            return hit

    # Step 4: search by filename (skip if same as metadata query)
    if query_filename and query_filename != query_metadata:
        hit = _try_search(query_filename, "search_filename")
        if hit:
            return hit

    return {"identified": False, "reason": "no match found via filename, metadata, or title search"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _yt_dlp() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def _extract_id_from_filename(path: Path) -> str | None:
    stem = path.stem

    m = _BRACKETED_RE.search(stem)
    if m:
        return m.group(1)

    m = _URL_RE.search(stem)
    if m and _plausible(m.group(1)):
        return m.group(1)

    stem_clean = _PAREN_RE.sub("", stem)
    for m in _BARE_RE.finditer(stem_clean):
        if _plausible(m.group(1)):
            return m.group(1)

    return None


def _plausible(s: str) -> bool:
    return any(c.isdigit() for c in s)


def _build_search_query(path: Path) -> str:
    return _PAREN_RE.sub("", path.stem).strip(" -|¦_")


def _build_search_query_from_tags(title: str | None, artist: str | None) -> str | None:
    """Build a YouTube search query from embedded title/artist tags, or None if no tags."""
    parts = [p.strip() for p in [artist, title] if p and p.strip()]
    return " ".join(parts) if parts else None


def _read_embedded_metadata(path: Path) -> tuple[str | None, float | None, str | None, str | None]:
    """Return (video_id_from_comment, original_duration, title, artist) from file metadata."""
    tags = get_tags(path)
    if not tags:
        return None, None, None, None

    video_id: str | None = None
    comment = tags.get("comment", "")
    # Match both "youtube:ID" and full URL forms
    m = re.search(r"youtube:([A-Za-z0-9_-]{11})", comment)
    if not m:
        m = re.search(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})", comment)
    if m:
        video_id = m.group(1)

    original_duration: float | None = None
    raw_dur = tags.get("original_duration")
    if raw_dur:
        try:
            original_duration = float(raw_dur)
        except ValueError:
            pass

    title = tags.get("title") or None
    artist = tags.get("artist") or tags.get("album_artist") or None

    return video_id, original_duration, title, artist


def _get_local_duration(path: Path) -> float | None:
    return get_duration(path)


def _duration_matches(
    yt_dur: float | None, local_dur: float | None, tolerance: float
) -> bool | None:
    if yt_dur is None or local_dur is None:
        return None
    return abs(yt_dur - local_dur) <= tolerance


def _fetch_video_info(video_id: str) -> dict | None:
    """Fetch title, channel, duration, description for a known video ID."""
    try:
        result = subprocess.run(
            [
                *_yt_dlp(),
                f"https://www.youtube.com/watch?v={video_id}",
                "--print",
                "%(title)s",
                "--print",
                "%(duration)s",
                "--print",
                "%(channel)s",
                "--print",
                "%(description)s",
                "--no-download",
                "--no-warnings",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    lines = result.stdout.split("\n")
    if not lines or not lines[0].strip():
        return None

    title = lines[0].strip()
    youtube_duration: float | None = None
    if len(lines) > 1:
        try:
            youtube_duration = float(lines[1].strip())
        except ValueError:
            pass
    channel = lines[2].strip() if len(lines) > 2 else None
    description = lines[3].strip() if len(lines) > 3 else None

    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title,
        "channel": channel or None,
        "youtube_duration": youtube_duration,
        "description": description or None,
    }


def _search_youtube(query: str) -> dict | None:
    """Search YouTube and return info dict for the top result, or None."""
    try:
        result = subprocess.run(
            [
                *_yt_dlp(),
                f"ytsearch1:{query}",
                "--print",
                "%(id)s",
                "--print",
                "%(title)s",
                "--print",
                "%(duration)s",
                "--print",
                "%(channel)s",
                "--print",
                "%(description)s",
                "--no-download",
                "--no-warnings",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    lines = result.stdout.split("\n")
    if not lines or not lines[0].strip():
        return None

    video_id = lines[0].strip()
    title = lines[1].strip() if len(lines) > 1 else ""
    youtube_duration: float | None = None
    if len(lines) > 2:
        try:
            youtube_duration = float(lines[2].strip())
        except ValueError:
            pass
    channel = lines[3].strip() if len(lines) > 3 else None
    description = lines[4].strip() if len(lines) > 4 else None

    if not video_id:
        return None

    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "title": title,
        "channel": channel or None,
        "youtube_duration": youtube_duration,
        "description": description or None,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Identify the YouTube source of a media file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--options", default="{}", type=json.loads)
    args = parser.parse_args()
    result = run(args.input, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
