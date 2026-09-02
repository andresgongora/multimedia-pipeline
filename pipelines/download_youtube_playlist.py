"""Pipeline: download_youtube_playlist — download and scrub an entire playlist.

Batch pipeline (see AGENTS.md "Pipeline contracts"): chains two existing
pipelines back to back, no per-file logic duplicated here.

Given a playlist URL:
  1. Download every eligible video/audio (pipelines.download_youtube_media)
     into a work directory — by default a hidden directory inside output_dir,
     or an explicit directory via work_dir.
  2. Batch-scrub every downloaded file into output_dir:
       - media_type="video" → pipelines.batch_scrub_youtube_media
       - media_type="audio" → pipelines.batch_scrub_youtube_podcast
 3. A file that downloaded fine but failed scrubbing is moved, unscrubbed,
      into output_dir as-is (never silently lost) instead of staying stuck
      in the work directory.
      A file whose scrub was skipped is not rescued; it is discarded with the
      work directory because its already-scrubbed output exists in output_dir.
  4. The work directory (hidden default or explicit work_dir) is removed
     once every file has landed somewhere in output_dir (scrubbed or, on
     scrub failure, raw) — even when explicitly supplied, it's still
     treated as disposable and wiped on every run.

db_path is optional and forwarded verbatim to pipelines.download_youtube_media
(see that pipeline's docstring) — when omitted, every playlist URL is
(re-)downloaded each run, with no persisted skip-list.

Config (pipelines/download_youtube_playlist.yaml):
    verbose         — print progress (default: true)
    download        — options forwarded to pipelines.download_youtube_media
    scrub_media     — options forwarded to pipelines.batch_scrub_youtube_media
                      (used when media_type == "video")
    scrub_podcast   — options forwarded to pipelines.batch_scrub_youtube_podcast
                      (used when media_type == "audio")

Usage:
    uv run -m pipelines.download_youtube_playlist PLAYLIST_URL /out video
    uv run -m pipelines.download_youtube_playlist PLAYLIST_URL /out audio --db state/podcasts.json
    uv run -m pipelines.download_youtube_playlist PLAYLIST_URL /out audio --work-dir /tmp/dl
"""

from __future__ import annotations

import shutil
from pathlib import Path

from shared.config import load_config
from shared.output import pipeline_log
import pipelines.batch_scrub_youtube_media as batch_scrub_youtube_media
import pipelines.batch_scrub_youtube_podcast as batch_scrub_youtube_podcast
import pipelines.download_youtube_media as download_youtube_media

_PIPELINE = "download_youtube_playlist"
_DEFAULT_CONFIG = Path(__file__).with_suffix(".yaml")

_WORK_DIR_NAME = ".~download_youtube_playlist~work"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rescue_unscrubbed(work_dir: Path, out_dir: Path, scrub_results: list[dict]) -> None:
    """Move any failed-scrub download from work_dir into out_dir, unscrubbed.

    Never overwrites an existing file: falls back to a disambiguated name.
    """
    for entry in scrub_results:
        if entry.get("status") != "failed":
            continue
        src = Path(entry["input_path"])
        if not src.exists():
            continue
        dest = out_dir / src.name
        if dest.exists():
            counter = 1
            while True:
                suffix = "" if counter == 1 else f".{counter}"
                dest = out_dir / f"{src.stem}.download{suffix}{src.suffix}"
                if not dest.exists():
                    break
                counter += 1
        try:
            shutil.move(str(src), str(dest))
        except Exception as exc:
            pipeline_log(_PIPELINE, f"[red]\u2717[/] rescue failed {src}: {exc}")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(
    playlist_url: str,
    output_dir: str,
    media_type: str,
    *,
    work_dir: str | None = None,
    db_path: str | None = None,
    force: bool = False,
    config_path: Path | None = None,
    options: dict | None = None,
) -> dict:
    """Download and scrub every eligible file in a playlist.

    work_dir is the directory downloads land in before scrubbing. Optional —
    defaults to a hidden directory inside output_dir. If given explicitly, it
    is used as-is (created if missing) instead; either way it is treated as
    disposable and removed once every file has landed in output_dir.

    Returns an aggregate result dict. `results` holds the scrub-phase
    per-file outcome (the pipeline's final artifact placement);
    `download_results` holds the raw download-phase per-URL outcome.

    Raises:
        ValueError: if media_type is invalid.
    """
    if media_type not in ("video", "audio"):
        raise ValueError(f"Unknown media_type '{media_type}'. Choose 'video' or 'audio'.")

    # ── 1. Config ─────────────────────────────────────────────────────────
    cfg = load_config(_DEFAULT_CONFIG, config_path, options)
    verbose: bool = cfg.get("verbose", True)
    download_opts = dict(cfg.get("download", {}))
    download_opts.setdefault("verbose", verbose)
    scrub_key = "scrub_media" if media_type == "video" else "scrub_podcast"
    scrub_opts = dict(cfg.get(scrub_key, {}))
    scrub_opts.setdefault("verbose", verbose)
    scrub_batch = batch_scrub_youtube_media if media_type == "video" else batch_scrub_youtube_podcast

    # ── 2. Prepare directories ──────────────────────────────────────────────
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir_path = Path(work_dir) if work_dir is not None else out_dir / _WORK_DIR_NAME
    work_dir_path.mkdir(parents=True, exist_ok=True)

    if verbose:
        pipeline_log(_PIPELINE, f"[cyan]{playlist_url}[/] → {out_dir}")

    try:
        # ── 3. Download phase ────────────────────────────────────────────────
        dl_result = download_youtube_media.run(
            playlist_url,
            str(work_dir_path),
            media_type,
            db_path=db_path,
            force=force,
            options=download_opts,
        )

        # ── 4. Scrub phase ───────────────────────────────────────────────────
        scrub_result = scrub_batch.run(
            str(work_dir_path),
            str(out_dir),
            force=force,
            options=scrub_opts,
        )

        # ── 5. Rescue any downloaded-but-unscrubbed file ─────────────────────
        _rescue_unscrubbed(work_dir_path, out_dir, scrub_result["results"])
    finally:
        shutil.rmtree(work_dir_path, ignore_errors=True)

    total_failed = dl_result["failed"] + scrub_result["failed"]
    if verbose:
        pipeline_log(
            _PIPELINE,
            f"[green]\u2713[/] {scrub_result['processed']} processed, "
            f"{scrub_result['skipped']} skipped, {total_failed} failed",
        )

    return {
        "playlist_url": playlist_url,
        "output_dir": str(out_dir),
        "downloaded": dl_result["downloaded"],
        "download_failed": dl_result["failed"],
        "processed": scrub_result["processed"],
        "skipped": scrub_result["skipped"],
        "scrub_failed": scrub_result["failed"],
        "failed": total_failed,
        "results": scrub_result["results"],
        "download_results": dl_result["results"],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Download and scrub an entire YouTube playlist.")
    parser.add_argument("playlist_url")
    parser.add_argument("output_dir")
    parser.add_argument("media_type", choices=["video", "audio"])
    parser.add_argument(
        "--work-dir",
        default=None,
        help="Download work directory (optional — default: hidden dir inside output_dir). Always wiped on completion.",
    )
    parser.add_argument("--db", default=None, help="Download registry JSON path (optional — omit to skip dedup)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--options", type=json.loads, default="{}")
    args = parser.parse_args()
    result = run(
        args.playlist_url,
        args.output_dir,
        args.media_type,
        work_dir=args.work_dir,
        db_path=args.db,
        force=args.force,
        config_path=args.config,
        options=args.options,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
