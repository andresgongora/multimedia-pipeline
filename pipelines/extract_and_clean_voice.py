"""Pipeline: extract_and_clean_voice — extract and clean voice from a video file.

Processes a single video file. Output is a WAV placed next to the original video.
Skips if output already exists unless force=True.

Config (pipelines/extract_and_clean_voice.yaml):
    verbose          — print progress to terminal (default: true)
    video_extensions — list of file extensions treated as video inputs
    stages.extract   — options forwarded to extract_audio stage
    stages.clean     — options forwarded to clean_recorded_voice stage

Usage:
    uv run -m pipelines.extract_and_clean_voice video.mp4
    uv run -m pipelines.extract_and_clean_voice video.mp4 --force
    uv run -m pipelines.extract_and_clean_voice /dir/of/videos -r
    uv run -m pipelines.extract_and_clean_voice video.mp4 -o /out/dir
    uv run -m pipelines.extract_and_clean_voice video.mp4 -o clean.wav
    uv run -m pipelines.extract_and_clean_voice video.mp4 --config my_config.yaml
"""

from __future__ import annotations

from pathlib import Path

from shared.config import load_config, propagate_verbose
from shared.io import safe_output_path
from shared.output import pipeline_log, pipeline_timer
import stages.extract_and_clean_voice as extract_and_clean_voice

_PIPELINE = "extract_and_clean_voice"
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
    """Process a single video file. Returns result dict."""

    # ── 1. Config ─────────────────────────────────────────────────────────
    cfg = load_config(_DEFAULT_CONFIG, config_path, options)
    verbose = cfg.get("verbose", True)
    video_exts = {e.lower() for e in cfg.get("video_extensions", [".mp4", ".mov", ".mkv"])}
    propagate_verbose(cfg)
    stage_opts = cfg.get("stages", {})

    # ── 2. Validate input ─────────────────────────────────────────────────
    video = Path(input_path)
    if not video.exists():
        raise FileNotFoundError(f"Input not found: {video}")
    if video.suffix.lower() not in video_exts:
        raise ValueError(f"Not a recognised video file: {video}")

    # ── 3. Resolve output path ────────────────────────────────────────────
    if output_path:
        output_wav = safe_output_path(video, Path(output_path))
    elif output_dir:
        out_parent = Path(output_dir)
        out_parent.mkdir(parents=True, exist_ok=True)
        output_wav = safe_output_path(video, out_parent / f"{video.stem}.wav")
    else:
        output_wav = safe_output_path(video, video.with_suffix(".wav"))

    # ── 4. Skip check ────────────────────────────────────────────────────
    if output_wav.exists() and not force:
        if verbose:
            pipeline_log(_PIPELINE, f"[dim]skip[/] {video.name} — output exists")
        return {"skipped": True, "input_path": str(video), "output_path": str(output_wav)}

    # ── 5. Execute ────────────────────────────────────────────────────────
    with pipeline_timer(_PIPELINE, video.name, verbose) as pt:
        result = extract_and_clean_voice.run(str(video), str(output_wav), options=stage_opts)
        result["input_path"] = str(video)
        pt["output"] = output_wav.name

    return result
