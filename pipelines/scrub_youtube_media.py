"""Pipeline: scrub_youtube_media — remove sponsored segments and clean up a media file.

Given a single media file (audio or video):
  1. Identify it on YouTube (by filename ID, embedded metadata, or title search).
  2. Fetch SponsorBlock segments for the identified video.
  3. Cut out skip-action segments (sponsors, intros, outros, etc.).
  4. Strip all privacy-sensitive metadata from the result.
  5. Embed clean metadata (title, artist/channel, YouTube comment tag,
     original YouTube duration) if identification succeeded.
  6. Suggest a clean filename and save alongside the original.

Stages degrade gracefully: if identification fails the file is still
scrubbed and noise is removed from its filename. If SponsorBlock has no
data the file is still processed through the metadata steps.

Config (pipelines/scrub_youtube_media.yaml):
    verbose              — print progress (default: true)
    stages.identify      — options for identify_youtube_media stage
    stages.sponsorblock  — options for fetch_sponsorblock_timestamps stage
    stages.cut           — options for cut stage
    stages.suggest_name  — options for suggest_name stage

Usage:
    uv run -m pipelines.scrub_youtube_media media.m4a
    uv run -m pipelines.scrub_youtube_media media.mp4 -o /out/dir
    uv run -m pipelines.scrub_youtube_media /dir/of/media -r
    uv run -m pipelines.scrub_youtube_media media.m4a --force
"""

from __future__ import annotations

from pathlib import Path

from shared.config import load_config, propagate_verbose
from shared.io import safe_output_path
from shared.output import pipeline_log, pipeline_timer
import stages.add_metadata as add_metadata
import stages.cut as cut
import stages.fetch_sponsorblock_timestamps as fetch_sponsorblock
import stages.identify_youtube_media as identify
import stages.scrub_metadata as scrub_metadata
import stages.suggest_name as suggest_name

_PIPELINE = "scrub_youtube_media"
_DEFAULT_CONFIG = Path(__file__).with_suffix(".yaml")


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
    """Process a single media file. Returns result dict."""

    # ── 1. Config ─────────────────────────────────────────────────────────
    cfg = load_config(_DEFAULT_CONFIG, config_path, options)
    verbose: bool = cfg.get("verbose", True)
    propagate_verbose(cfg)
    stage_cfg = cfg.get("stages", {})

    # ── 2. Validate input ─────────────────────────────────────────────────
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")

    # ── 3. Resolve output directory (for temps and final naming) ──────────
    out_dir = Path(output_dir) if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── 4. Execute stages ─────────────────────────────────────────────────
    temps: list[Path] = []

    def _temp(stage: str) -> Path:
        p = out_dir / f".~{stage}~{src.name}"
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

            # Cut
            temp_cut = _temp("cut")
            cut.run(
                str(src),
                str(temp_cut),
                remove_ranges,
                options={
                    **stage_cfg.get("cut", {}),
                    "verbose": verbose,
                },
            )
            current = temp_cut

            # Scrub metadata
            temp_scrub = _temp("scrub_metadata")
            scrub_metadata.run(str(current), str(temp_scrub), options={"verbose": verbose})
            current = temp_scrub

            # Add metadata (skip if not identified)
            if id_result["identified"]:
                fields: dict[str, str] = {}
                if id_result.get("title"):
                    fields["title"] = id_result["title"]
                if id_result.get("channel"):
                    fields["artist"] = id_result["channel"]
                fields["comment"] = f"youtube:{id_result['video_id']}"
                if id_result.get("youtube_duration") is not None:
                    fields["ORIGINAL_DURATION"] = f"{id_result['youtube_duration']:.2f}"
                if remove_ranges:
                    removed_s = sum(e - s for s, e in remove_ranges)
                    fields["SCRUBBED"] = f"{removed_s:.2f}"
                temp_meta = _temp("add_metadata")
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
            # Pass the original source file so suggest_name reads its clean
            # filename/metadata — not the temp file's mangled name.
            name_result = suggest_name.run(
                str(src),
                options={
                    **stage_cfg.get("suggest_name", {}),
                    "verbose": False,
                },
            )
            suggested = name_result["suggested_name"]

            if output_path:
                final = safe_output_path(src, Path(output_path))
            else:
                final = safe_output_path(src, out_dir / (suggested + src.suffix))

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
