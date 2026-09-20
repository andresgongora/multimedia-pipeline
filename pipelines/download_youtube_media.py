"""Pipeline: download_youtube_media — download videos in a public playlist.

Given a playlist URL:
  1. List every video URL in the playlist.
  2. If db_path is given, filter out URLs already in the download registry.
  3. For each remaining URL, download audio or video (stages.download_youtube_media
     defaults: 1080p/av1 video, best native audio, original language).
  4. If db_path is given, record each successful URL in the registry.
  5. On failure (download error, unsupported URL, etc.), log and skip —
     the URL is NOT recorded, so the next run retries it.

No further processing (no SponsorBlock, no metadata scrubbing, no
filename cleanup beyond embedding the video title). Chain other pipelines
on the output directory afterward if needed.

db_path is optional. When omitted, no dedup registry is used: every playlist
URL is (re-)downloaded each run, with no persisted skip-list.

Output filename: "{sanitized title} [{video_id}]{ext}". The bracketed
video ID lets downstream pipelines (e.g. scrub_youtube_media) identify the
file by filename without a search fallback.

Default container: ".mkv" for video, ".mka" for audio — both accept
arbitrary codecs (av1, opus, ...) via stream copy, avoiding remux failures
that a stricter container (mp4/m4a) would hit for opus-only audio
streams. See .agent/decisions/download-media-container-format.md.

Config (pipelines/download_youtube_media.yaml):
    verbose            — print progress (default: true)
    max_age_days       — registry entry lifetime in days (default: infinite;
                         set a number to expire entries)
    stages.download    — options for stages.download_youtube_media
                         (resolution, video_codec, language)
    video_ext          — output extension for media_type="video" (default: ".mkv")
    audio_ext          — output extension for media_type="audio" (default: ".mka")

Usage:
    uv run -m pipelines.download_youtube_media PLAYLIST_URL /out/dir video --db state/videos.json
    uv run -m pipelines.download_youtube_media PLAYLIST_URL /out/dir audio --db state/videos.json
    uv run -m pipelines.download_youtube_media PLAYLIST_URL /out/dir video
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import stages.download_youtube_media as download_youtube_media
import stages.fetch_youtube_playlist as fetch_youtube_playlist
from shared import download_registry as registry
from shared.config import load_config, propagate_verbose
from shared.io import sanitize_filename
from shared.output import pipeline_log

_PIPELINE = "download_youtube_media"
_DEFAULT_CONFIG = Path(__file__).with_suffix(".yaml")

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})")


def _extract_video_id(url: str) -> str | None:
    m = _VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(
    playlist_url: str,
    output_dir: str,
    media_type: str,
    *,
    db_path: str | None = None,
    force: bool = False,
    config_path: Path | None = None,
    options: dict | None = None,
) -> dict:
    """Download every new video in a playlist. Returns aggregate result dict.

    Raises:
        ValueError: if media_type is invalid.
    """
    if media_type not in ("video", "audio"):
        raise ValueError(f"Unknown media_type '{media_type}'. Choose 'video' or 'audio'.")

    # ── 1. Config ─────────────────────────────────────────────────────────
    cfg = load_config(_DEFAULT_CONFIG, config_path, options)
    verbose: bool = cfg.get("verbose", True)
    propagate_verbose(cfg)
    max_age_days = cfg.get("max_age_days", None)
    download_opts = dict(cfg.get("stages", {}).get("download", {}))
    ext = cfg.get("video_ext", ".mkv") if media_type == "video" else cfg.get("audio_ext", ".mka")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    db = Path(db_path) if db_path is not None else None

    # ── 2. Fetch playlist & filter against registry ───────────────────────
    start = time.monotonic()
    if verbose:
        pipeline_log(_PIPELINE, f"[cyan]{playlist_url}[/]")

    urls = fetch_youtube_playlist.run(playlist_url, options={"verbose": verbose})["video_urls"]
    new_urls = registry.filter_new(urls, db, max_age_days=max_age_days) if db is not None else urls

    if verbose:
        pipeline_log(
            _PIPELINE,
            f"{len(urls)} in playlist, {len(new_urls)} new (max_age_days={max_age_days})",
        )

    # ── 3. Per-URL download ────────────────────────────────────────────────
    results: list[dict] = []
    downloaded = 0
    skipped_existing = 0
    failed = 0

    for i, url in enumerate(new_urls, 1):
        count = f"[{i}/{len(new_urls)}] "
        video_id = _extract_video_id(url)
        if not video_id:
            if verbose:
                pipeline_log(_PIPELINE, f"{count}[red]✗[/] {url}: could not extract video ID")
            failed += 1
            results.append({"url": url, "status": "failed", "reason": "no video ID in URL"})
            continue

        # Placeholder name until we know the title (download stage returns it).
        # We must pick the final dst path before downloading (stage requires
        # output_path upfront), so probe for an existing bracket match first.
        # (glob() is avoided here: "[id]" would be parsed as a glob character
        # class, not a literal bracket — plain substring scan instead.)
        marker = f"[{video_id}]{ext}"
        existing = next((p for p in out_dir.iterdir() if p.name.endswith(marker)), None)
        if existing is not None and not force:
            if verbose:
                pipeline_log(_PIPELINE, f"{count}[yellow]skip[/] {existing.name} (already on disk)")
            skipped_existing += 1
            results.append({"url": url, "status": "skipped_existing", "output_path": str(existing)})
            continue

        # Download to a provisional path named by video_id; rename once we
        # know the real title (returned by the stage after download).
        provisional = out_dir / f"{video_id}{ext}"
        if provisional.exists() and force:
            provisional.unlink()

        if verbose:
            pipeline_log(_PIPELINE, f"{count}[cyan]{video_id}[/]")

        try:
            dl_result = download_youtube_media.run(
                url,
                str(provisional),
                options={**download_opts, "media_type": media_type, "verbose": verbose},
            )
            title = dl_result.get("title")
            if title:
                final_name = f"{sanitize_filename(title)} [{video_id}]{ext}"
            else:
                final_name = provisional.name
            final = out_dir / final_name
            if final != provisional:
                if final.exists():
                    final.unlink()
                provisional.rename(final)

            if db is not None:
                registry.record(url, db, metadata={"video_id": video_id, "title": title})
            downloaded += 1
            results.append({"url": url, "status": "downloaded", "output_path": str(final)})
            if verbose:
                pipeline_log(_PIPELINE, f"{count}[green]\u2713[/] {final.name}")
        except Exception as exc:
            failed += 1
            results.append({"url": url, "status": "failed", "reason": str(exc)})
            if verbose:
                pipeline_log(_PIPELINE, f"{count}[red]\u2717[/] {url}: {exc}")
            continue

    if verbose:
        elapsed = time.monotonic() - start
        pipeline_log(
            _PIPELINE,
            f"[green]\u2713[/] {downloaded} downloaded, {skipped_existing} skipped, "
            f"{failed} failed ({elapsed:.1f}s)",
        )

    return {
        "playlist_url": playlist_url,
        "requested": len(urls),
        "new": len(new_urls),
        "downloaded": downloaded,
        "skipped_known": len(urls) - len(new_urls),
        "skipped_existing": skipped_existing,
        "failed": failed,
        "results": results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Download every new video in a YouTube playlist.")
    parser.add_argument("playlist_url")
    parser.add_argument("output_dir")
    parser.add_argument("media_type", choices=["video", "audio"])
    parser.add_argument(
        "--db", default=None, help="Download registry JSON path (optional — omit to skip dedup)"
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--options", type=json.loads, default="{}")
    args = parser.parse_args()
    result = run(
        args.playlist_url,
        args.output_dir,
        args.media_type,
        db_path=args.db,
        force=args.force,
        config_path=args.config,
        options=args.options,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
