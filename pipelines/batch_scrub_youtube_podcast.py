"""Pipeline: batch_scrub_youtube_podcast — scrub every eligible podcast file in a folder.

Batch pipeline (see AGENTS.md "Pipeline contracts"): aggregate operation over
many discovered items, no single input/output file. Delegates the actual
per-file work to pipelines.scrub_youtube_podcast via shared.batch.run_dir_batch
— no scrub logic is duplicated here.

Given an input directory:
  1. Discover every file directly inside it with a recognised audio extension
     (non-recursive).
  2. Run pipelines.scrub_youtube_podcast on each file, writing output into
     output_dir.
  3. Collect a per-file result; one failure does not stop the batch.

Mirrors the core loop of wrapper_scripts/process_podcast_inbox.sh (find
eligible files, process each, force-overwrite, keep going on failure), but
stays general-purpose: it does not trash/move the original file and does not
invent a dated output subfolder — those are personal workflow choices that
stay in the wrapper script. This pipeline only ever writes to output_dir; it
never touches input_dir.

Config (pipelines/batch_scrub_youtube_podcast.yaml):
    verbose     — print progress (default: true)
    extensions  — file extensions treated as candidate inputs
    pipeline    — options forwarded to pipelines.scrub_youtube_podcast

Usage:
    uv run -m pipelines.batch_scrub_youtube_podcast /inbox /out
    uv run -m pipelines.batch_scrub_youtube_podcast /inbox /out --force
"""

from __future__ import annotations

from pathlib import Path

import pipelines.scrub_youtube_podcast as scrub_youtube_podcast
from shared.batch import run_dir_batch
from shared.config import load_config

_PIPELINE = "batch_scrub_youtube_podcast"
_DEFAULT_CONFIG = Path(__file__).with_suffix(".yaml")

_AUDIO_EXTS = [".m4a", ".mp3", ".opus", ".flac", ".wav", ".ogg", ".aac", ".mka"]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(
    input_dir: str,
    output_dir: str,
    *,
    force: bool = False,
    config_path: Path | None = None,
    options: dict | None = None,
) -> dict:
    """Scrub every eligible podcast file directly inside input_dir.

    Returns an aggregate result dict with a per-file `results` list.

    Raises:
        NotADirectoryError: if input_dir is not an existing directory.
    """
    cfg = load_config(_DEFAULT_CONFIG, config_path, options)
    verbose: bool = cfg.get("verbose", True)
    exts = {e.lower() for e in cfg.get("extensions", _AUDIO_EXTS)}
    pipeline_opts = dict(cfg.get("pipeline", {}))
    pipeline_opts.setdefault("verbose", verbose)

    return run_dir_batch(
        _PIPELINE,
        scrub_youtube_podcast.run,
        input_dir,
        output_dir,
        exts,
        force=force,
        pipeline_options=pipeline_opts,
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Scrub every eligible podcast file in a folder.")
    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--options", type=json.loads, default="{}")
    args = parser.parse_args()
    result = run(
        args.input_dir,
        args.output_dir,
        force=args.force,
        config_path=args.config,
        options=args.options,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
