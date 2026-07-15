"""Stage: fetch_sponsorblock_timestamps — query SponsorBlock for flagged segments.

Fetches timestamped segments for a YouTube video from the SponsorBlock API
(https://sponsor.ajay.app). Returns all enabled categories in a single request
— the API accepts a list of categories, so no extra calls per category.

SponsorBlock categories:
  sponsor       — Paid sponsorship segments
  selfpromo     — Creator's own unpaid promotions / merch
  interaction   — "Like and subscribe" calls-to-action
  intro         — Recurring intro animation or still frame
  outro         — End credits / endcard screen
  preview       — Recap or preview clips
  hook          — Greeting / narrated trailer at the start
  filler        — Tangents, jokes, B-roll (aggressive — use with care)
  music_offtopic — Non-music speech in music-primary videos

The privacy API option sends only the first 4 hex chars of the SHA-256 hash of
the video ID, hiding the exact video from SponsorBlock's server logs.

Inputs:
    video_id — 11-character YouTube video ID

Options:
    categories      — list of category names to fetch; fetches all enabled ones
                      by default (see DEFAULTS below)
    use_privacy_api — use SHA-256 prefix endpoint instead of plain video ID
                      (default: False)
    base_url        — SponsorBlock API base URL (default: "https://sponsor.ajay.app")
    ssl_verify      — verify SSL certificates; set False to bypass self-signed /
                      intercepting proxy certs (default: True)
    verbose         — print progress (default: True)

Returns:
    {
      "video_id":  "dQw4w9WgXcQ",
      "found":     True,
      "segments": [
        {
          "start":       12.5,
          "end":         83.2,
          "category":    "sponsor",
          "action_type": "skip",
          "uuid":        "...",
          "votes":       42,
          "locked":      false,
        },
        ...
      ]
    }

    When nothing is found:
    {
      "video_id": "dQw4w9WgXcQ",
      "found":    False,
      "segments": []
    }

Example usage:
    result = run("dQw4w9WgXcQ")

    result = run("dQw4w9WgXcQ", options={
        "categories": ["sponsor", "selfpromo"],
        "use_privacy_api": True,
    })

    # CLI
    uv run -m stages.fetch_sponsorblock_timestamps --video-id dQw4w9WgXcQ
    uv run -m stages.fetch_sponsorblock_timestamps --video-id dQw4w9WgXcQ \\
        --options '{"categories": ["sponsor", "intro", "outro"]}'
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time

import httpx

from shared.output import stage_header, stage_log, stage_timer

_STAGE = "fetch_sponsorblock_timestamps"

# Defaults mirror old/youtube-scrubber/config.yaml [fetch_sponsor_block]
DEFAULTS: dict = {
    "categories": [
        "sponsor",
        "selfpromo",
        "interaction",
        "intro",
        "outro",
        # "preview"       — disabled: may contain real content
        # "hook"          — disabled
        "filler",
        # "music_offtopic" — disabled
    ],
    "use_privacy_api": False,
    "base_url": "https://sponsor.ajay.app",
    "ssl_verify": True,
    "verbose": True,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(video_id: str, *, options: dict | None = None) -> dict:
    opts = {**DEFAULTS, **(options or {})}
    verbose: bool = opts["verbose"]
    categories: list[str] = opts["categories"]
    use_privacy: bool = opts["use_privacy_api"]
    base_url: str = opts["base_url"].rstrip("/")
    ssl_verify: bool = opts["ssl_verify"]

    if verbose:
        stage_log(_STAGE, f"[cyan]{video_id}[/] [dim]({len(categories)} categories)[/]")

    with stage_timer(_STAGE, "SponsorBlock queried"):
        segments = _fetch(video_id, categories, use_privacy, base_url, ssl_verify)

    if verbose:
        if segments:
            total_seconds = sum(seg["end"] - seg["start"] for seg in segments)
            stage_log(_STAGE, f"[dim]{len(segments)} segment(s), {total_seconds:.1f}s to cut[/]")
        else:
            stage_log(_STAGE, f"[dim]no segments found[/]")

    return {
        "video_id": video_id,
        "found": len(segments) > 0,
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _fetch(
    video_id: str, categories: list[str], use_privacy: bool, base_url: str, ssl_verify: bool = True
) -> list[dict]:
    params: dict = {"categories": json.dumps(categories)}

    if use_privacy:
        prefix = hashlib.sha256(video_id.encode()).hexdigest()[:4]
        url = f"{base_url}/api/skipSegments/{prefix}"
    else:
        url = f"{base_url}/api/skipSegments"
        params["videoID"] = video_id

    # Courtesy delay — not a poll-wait. Intentional rate-limiting to avoid
    # hammering the SponsorBlock API when processing batches of files.
    time.sleep(0.5)

    with httpx.Client(timeout=15.0, verify=ssl_verify) as client:
        response = client.get(url, params=params)

    if response.status_code == 404:
        return []

    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "json" not in content_type:
        # Non-JSON response means the request likely never reached SponsorBlock.
        # Most common causes:
        #  - ISP block page (e.g., Cloudflare IP blocks in some regions)
        #  - Captive portal / transparent proxy response
        #
        # Quick diagnosis (copy/paste):
        #   curl -v 'https://sponsor.ajay.app/api/skipSegments?videoID=dQw4w9WgXcQ&categories=%5B%22sponsor%22%5D'
        #
        # If output is HTML / legal notice instead of JSON, this is network-side.
        # Proceed as passthrough so pipeline can continue.
        import warnings

        warnings.warn(
            f"SponsorBlock returned non-JSON response (content-type: {content_type!r}). "
            "Likely ISP/proxy block; proceeding without SponsorBlock data.",
            stacklevel=3,
        )
        return []

    data = response.json()

    if use_privacy:
        # Privacy endpoint returns a list of {videoID, segments} objects
        segments_raw: list[dict] = []
        for entry in data:
            if entry.get("videoID") == video_id:
                segments_raw = entry.get("segments", [])
                break
    else:
        segments_raw = data

    return [_parse(raw) for raw in segments_raw]


def _parse(raw: dict) -> dict:
    start, end = raw["segment"]
    return {
        "start": float(start),
        "end": float(end),
        "category": raw["category"],
        "action_type": raw["actionType"],
        "uuid": raw["UUID"],
        "votes": int(raw.get("votes", 0)),
        "locked": bool(raw.get("locked", 0)),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Fetch SponsorBlock segments for a YouTube video.")
    parser.add_argument("--video-id", required=True, dest="video_id")
    parser.add_argument("--options", default="{}", type=json.loads)
    args = parser.parse_args()
    result = run(args.video_id, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
