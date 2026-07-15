"""Stage: suggest_name — suggest a clean filename for a media file.

Reads embedded metadata and/or the existing filename to produce a recommended
name (stem only, no extension). Does not touch the file.

Two strategies, tried in order:

  1. Metadata — reads title/artist from embedded tags and formats them.
     Requires at least one of: title, artist/album_artist.

  2. Scrub — strips technical noise from the existing filename (codec/quality
     tokens, resolution badges, pipe characters, underscores, …).

If neither strategy produces a useful name, returns the original stem unchanged.

Format string placeholders (strategy 1):
  {title}   — "title" tag
  {artist}  — "artist" tag (falls back to "album_artist")
  {album}   — "album" tag
  Missing placeholder values are replaced with empty string; dangling
  separators (e.g. " - ") are collapsed automatically.

Inputs:
    input_path — path to the media file

Options:
    format  — format string for metadata strategy (default: "{artist} - {title}")
    verbose — print progress (default: True)

Returns:
    {
      "suggested_name": "Artist - Title",   # stem only, no extension
      "strategy":       "metadata" | "scrub" | "none",
    }

Example usage:
    result = run("podcast [dQw4w9WgXcQ].m4a")
    # → {"suggested_name": "Rick Astley - Never Gonna Give You Up", "strategy": "metadata"}

    result = run("video.mp4", options={"format": "{title}"})

    # CLI
    uv run -m stages.suggest_name --input podcast.m4a
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from shared.ffprobe import get_tags
from shared.output import stage_header, stage_log, stage_timer

_STAGE = "suggest_name"

DEFAULTS: dict = {
    "format": "{artist} - {title}",
    "verbose": True,
}

# ---------------------------------------------------------------------------
# Filename noise-stripping rules
# ---------------------------------------------------------------------------

_RULES: list[tuple[str, str]] = [
    (r"[^\x20-\x7E\u00A0-\uFFFF]", ""),
    (r"\([^)]*(?:kbps|fps|AAC|kbit|AV1|VP9|HEVC|x264|x265|H\.?264|H\.?265)[^)]*\)", ""),
    (r"\(\s*[\dA-Za-z]+[_\-][\w\-]*\s*\)", ""),
    (r"\b(?:4320|2160|1440|1080|720|480|360|240)p\b", ""),
    (r"\s*[|¦]\s*", " "),
    (r"[¿?;¡!]", ""),
    (r"_", " "),
    (r"\.{2,}", "."),
    (r"\.\s*$", ""),
    (r" {2,}", " "),
    (r"^ | $", ""),
]
_COMPILED = [(re.compile(p), r) for p, r in _RULES]

_UNSAFE_RE = re.compile(r'[/\\:<>"|?*]')
_DANGLING_SEP_RE = re.compile(r"(\s*-\s*){2,}|^\s*-+\s*|-+\s*$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(input_path: str, *, options: dict | None = None) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    verbose: bool = opts["verbose"]
    fmt: str = opts["format"]

    src = Path(input_path)

    if verbose:
        stage_header(_STAGE, src)

    with stage_timer(_STAGE, "read metadata"):
        tags = _read_tags(src)

    # Strategy 1: metadata
    name = _from_metadata(tags, fmt)
    strategy = "metadata"

    # Strategy 2: scrub filename
    if not name:
        name = _scrub(src.stem)
        strategy = "scrub"

    # Fallback: original stem
    if not name:
        name = src.stem
        strategy = "none"

    if verbose:
        stage_log(_STAGE, f"[dim]{strategy}:[/] {name!r}")

    return {"suggested_name": name, "strategy": strategy}


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


def _from_metadata(tags: dict, fmt: str) -> str:
    title = tags.get("title", "").strip()
    artist = (tags.get("artist") or tags.get("album_artist") or "").strip()
    album = tags.get("album", "").strip()

    if not title and not artist:
        return ""

    raw = fmt.format(
        title=_sanitize(_scrub(title)),
        artist=_sanitize(_scrub(artist)),
        album=_sanitize(_scrub(album)),
    ).strip()

    result = _DANGLING_SEP_RE.sub(" - ", raw).strip(" -")
    return re.sub(r" {2,}", " ", result).strip()


def _scrub(stem: str) -> str:
    result = stem
    for pattern, repl in _COMPILED:
        result = pattern.sub(repl, result)
    return result.strip()


def _sanitize(value: str) -> str:
    return re.sub(r" {2,}", " ", _UNSAFE_RE.sub("", value)).strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_tags(path: Path) -> dict:
    return get_tags(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Suggest a clean filename for a media file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--options", default="{}", type=json.loads)
    args = parser.parse_args()
    result = run(args.input, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
