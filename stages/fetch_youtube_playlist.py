"""Stage: fetch_youtube_playlist — list video URLs contained in a public YouTube playlist.

Uses yt-dlp with --flat-playlist (no per-video metadata fetch) to enumerate
every video in a public playlist quickly.

Inputs:
    playlist_url — URL of a public YouTube playlist

Options:
    verbose — print progress (default: True)

Returns:
    {
      "playlist_url": "...",
      "video_urls":   ["https://www.youtube.com/watch?v=...", ...],
      "count":        42,
    }

Example usage:
    result = run("https://www.youtube.com/playlist?list=PL...")

    # CLI
    uv run -m stages.fetch_youtube_playlist --input "https://www.youtube.com/playlist?list=PL..."
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

from shared.output import stage_header, stage_timer

_STAGE = "fetch_youtube_playlist"

DEFAULTS: dict = {
    "verbose": True,
}


def _yt_dlp() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def run(playlist_url: str, *, options: dict | None = None) -> dict:
    """List video URLs contained in a public playlist.

    Raises:
        RuntimeError: if yt-dlp fails to fetch the playlist.
    """
    opts = {**DEFAULTS, **(options or {})}
    verbose = opts["verbose"]

    if verbose:
        stage_header(_STAGE, playlist_url)

    with stage_timer(_STAGE, "done"):
        try:
            result = subprocess.run(
                [
                    *_yt_dlp(),
                    playlist_url,
                    "--flat-playlist",
                    "--print",
                    "%(url)s",
                    "--no-warnings",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"yt-dlp failed (exit {e.returncode}):\n{e.stderr.strip()}") from e
        except FileNotFoundError as e:
            raise RuntimeError("yt-dlp is not installed") from e

    video_urls = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    return {
        "playlist_url": playlist_url,
        "video_urls": video_urls,
        "count": len(video_urls),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="List video URLs in a public YouTube playlist.")
    parser.add_argument("--input", required=True, help="Playlist URL")
    parser.add_argument("--options", type=json.loads, default="{}", help="JSON options")
    args = parser.parse_args()
    result = run(args.input, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
