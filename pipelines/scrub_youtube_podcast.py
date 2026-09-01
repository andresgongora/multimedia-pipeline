"""Pipeline: scrub_youtube_podcast — scrub a YouTube podcast and enhance for listening.

Given a single audio file downloaded from YouTube:
  1. Identify the file on YouTube (by filename ID, metadata, or title search).
  2. Fetch SponsorBlock segments (sponsors, intros, outros, etc.).
  3. Convert source audio to a lossless WAV working file.
  4. Cut out skip-action segments (precise mode).
  5. Remove silences (optional, enabled by default).
  6. Apply podcast filter once → final M4A encode.
  7. Scrub all privacy-sensitive metadata.
  8. Embed clean metadata (title, channel, duration, processing tag).
  9. Suggest a clean filename and save alongside the original.

Only accepts audio input (video raises ValueError with a hint).
Always outputs .m4a regardless of input format.

Config (pipelines/scrub_youtube_podcast.yaml):
    verbose                  — print progress (default: true)
    stages.identify          — options for identify_youtube_media stage
    stages.sponsorblock      — options for fetch_sponsorblock_timestamps stage
    stages.convert_to_wav    — options for convert_to_wav stage
    stages.cut               — options for cut stage (mode forced to "precise")
    stages.remove_silences   — options for remove_silences stage
                               set enabled: false to skip
    stages.filter            — options for filter_podcast_audio stage
    stages.suggest_name      — options for suggest_name stage

Usage:
    uv run -m pipelines.scrub_youtube_podcast podcast.opus
    uv run -m pipelines.scrub_youtube_podcast podcast.m4a -o /out/dir
    uv run -m pipelines.scrub_youtube_podcast /dir/of/podcasts -r
    uv run -m pipelines.scrub_youtube_podcast podcast.opus --force
"""

from __future__ import annotations

import warnings
from pathlib import Path

from shared.config import load_config, propagate_verbose
from shared.ffprobe import get_duration
from shared.io import safe_output_path
from shared.output import pipeline_timer
import stages.add_metadata as add_metadata
import stages.convert_to_wav as convert_to_wav
import stages.cut as cut
import stages.fetch_sponsorblock_timestamps as fetch_sponsorblock
import stages.filter_podcast_audio as filter_podcast_audio
import stages.identify_youtube_media as identify
import stages.remove_silences as remove_silences
import stages.scrub_metadata as scrub_metadata
import stages.suggest_name as suggest_name

_PIPELINE = "scrub_youtube_podcast"
_DEFAULT_CONFIG = Path(__file__).with_suffix(".yaml")

_AUDIO_EXTS = {".m4a", ".mp3", ".opus", ".flac", ".wav", ".ogg", ".aac"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".webm"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_local_duration(path: Path) -> float | None:
    """Return duration of *path* in seconds via ffprobe, or None on failure."""
    return get_duration(path)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(
    input_path: str,
    *,
    output_dir: str | None = None,
    output_path: str | None = None,
    force: bool = False,
    config_path: Path | None = None,
    options: dict | None = None,
) -> dict:
    """Process a single audio file. Returns result dict."""

    # ── 1. Config ─────────────────────────────────────────────────────────
    cfg = load_config(_DEFAULT_CONFIG, config_path, options)
    verbose: bool = cfg.get("verbose", True)
    propagate_verbose(cfg)
    stage_cfg = cfg.get("stages", {})

    filter_opts = dict(stage_cfg.get("filter", {}))
    filter_final_opts = {**filter_opts, "output_format": "m4a", "verbose": verbose}

    rs_cfg = stage_cfg.get("remove_silences", {})
    rs_enabled = rs_cfg.get("enabled", True)
    rs_opts = {k: v for k, v in rs_cfg.items() if k != "enabled"}

    # ── 2. Validate input ─────────────────────────────────────────────────
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")

    ext = src.suffix.lower()
    if ext in _VIDEO_EXTS:
        raise ValueError(
            f"scrub_youtube_podcast only accepts audio files; got video: {src.name}\n"
            "  Hint: extract audio first with extract_audio, or use scrub_youtube_media."
        )
    if ext not in _AUDIO_EXTS:
        warnings.warn(
            f"Unknown extension '{ext}' for {src.name}; proceeding but results may vary.",
            stacklevel=2,
        )

    # ── 3. Resolve output directory ───────────────────────────────────────
    out_dir = Path(output_dir) if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 4. Execute stages ─────────────────────────────────────────────────
    temps: list[Path] = []

    def _temp(stage: str, suffix: str = src.suffix) -> Path:
        p = out_dir / f".~{stage}~{src.stem}{suffix}"
        temps.append(p)
        return p

    with pipeline_timer(_PIPELINE, src.name, verbose) as pt:
        try:
            # Identify
            id_result = identify.run(
                str(src),
                options={
                    **stage_cfg.get("identify", {}),
                    "verbose": verbose,
                },
            )

            # SponsorBlock
            remove_ranges: list[list[float]] = []
            sb_result: dict = {"found": False, "segments": []}

            if id_result["identified"]:
                sb_result = fetch_sponsorblock.run(
                    id_result["video_id"],
                    options={
                        **stage_cfg.get("sponsorblock", {}),
                        "verbose": verbose,
                    },
                )
                remove_ranges = [
                    [s["start"], s["end"]]
                    for s in sb_result["segments"]
                    if s["action_type"] == "skip"
                ]

            # Convert to WAV work file
            temp_wav = _temp("convert_to_wav", ".wav")
            convert_to_wav.run(
                str(src),
                str(temp_wav),
                options={
                    **(stage_cfg.get("convert_to_wav") or {}),
                    "verbose": verbose,
                },
            )
            current = temp_wav

            # Cut (precise)
            temp_cut = _temp("cut", ".wav")
            cut.run(
                str(current),
                str(temp_cut),
                remove_ranges,
                options={
                    **stage_cfg.get("cut", {}),
                    "mode": "precise",
                    "verbose": verbose,
                },
            )
            current = temp_cut

            # Remove silences (optional)
            if rs_enabled:
                temp_rs = _temp("remove_silences", ".wav")
                remove_silences.run(
                    str(current),
                    str(temp_rs),
                    options={
                        **rs_opts,
                        "verbose": verbose,
                    },
                )
                current = temp_rs

            # Podcast filter → M4A (final encode)
            temp_filtered_final = _temp("filter_final", ".m4a")
            filter_podcast_audio.run(str(current), str(temp_filtered_final), options=filter_final_opts)
            current = temp_filtered_final

            # Scrub metadata
            temp_scrub = _temp("scrub_metadata", ".m4a")
            scrub_metadata.run(str(current), str(temp_scrub), options={"verbose": verbose})
            current = temp_scrub

            # Add metadata
            fields: dict[str, str] = {}
            if id_result["identified"]:
                if id_result.get("title"):
                    fields["title"] = id_result["title"]
                if id_result.get("channel"):
                    fields["artist"] = id_result["channel"]
                fields["comment"] = f"youtube:{id_result['video_id']}"
                if remove_ranges:
                    removed_s = sum(e - s for s, e in remove_ranges)
                    fields["SCRUBBED"] = f"{removed_s:.2f}"
            orig_dur = id_result.get("youtube_duration") if id_result["identified"] else None
            if orig_dur is None:
                orig_dur = _get_local_duration(src)
            if orig_dur is not None:
                fields["ORIGINAL_DURATION"] = f"{orig_dur:.2f}"
            fields["PROCESSED_BY"] = _PIPELINE
            temp_meta = _temp("add_metadata", ".m4a")
            add_metadata.run(
                str(current),
                str(temp_meta),
                options={
                    "fields": fields,
                    "verbose": verbose,
                },
            )
            current = temp_meta

            # ── 5. Suggest name & finalize ────────────────────────────────────
            name_result = suggest_name.run(
                str(current),
                options={
                    **stage_cfg.get("suggest_name", {}),
                    "verbose": False,
                },
            )
            suggested = name_result["suggested_name"]

            if output_path:
                final = safe_output_path(src, Path(output_path))
            else:
                final = safe_output_path(src, out_dir / (suggested + ".m4a"))

            if final.exists() and not force:
                raise FileExistsError(f"Output already exists: {final}  (use --force to overwrite)")
            if final.exists():
                final.unlink()

            current.rename(final)
            pt["output"] = final.name

            return {
                "output_path": str(final),
                "identified": id_result["identified"],
                "video_id": id_result.get("video_id"),
                "removed_segments": len(remove_ranges),
                "suggested_name": suggested,
                "sponsorblock_found": sb_result["found"],
            }

        finally:
            for t in temps:
                t.unlink(missing_ok=True)
