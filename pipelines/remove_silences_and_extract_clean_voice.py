"""Pipeline: remove_silences_and_extract_clean_voice — trim silence, then clean audio.

Processes a single video file. Writes:
  - a silence-trimmed video next to the original (configurable suffix)
  - a cleaned WAV extracted from that trimmed video (configurable suffix)

Config (pipelines/remove_silences_and_extract_clean_voice.yaml):
    verbose            — print progress to terminal (default: true)
    video_extensions   — list of file extensions treated as video inputs
    output.video_suffix — suffix appended to trimmed video stem
    output.audio_suffix — suffix appended to cleaned audio stem
    stages.sanitize    — options forwarded to sanitize_video stage
    stages.remove      — options forwarded to remove_silences stage
    stages.extract     — options forwarded to extract_audio stage
    stages.clean       — options forwarded to clean_recorded_voice stage

Usage:
    uv run -m pipelines.remove_silences_and_extract_clean_voice video.mp4
    uv run -m pipelines.remove_silences_and_extract_clean_voice video.mp4 --force
    uv run -m pipelines.remove_silences_and_extract_clean_voice /dir/of/videos -r
    uv run -m pipelines.remove_silences_and_extract_clean_voice video.mp4 -o /out/dir
"""

from __future__ import annotations

from pathlib import Path

from shared.config import load_config, propagate_verbose
from shared.io import safe_output_path
from shared.output import pipeline_log, pipeline_timer
import stages.extract_and_clean_voice as extract_and_clean_voice
import stages.remove_silences as remove_silences
import stages.sanitize_video as sanitize_video

_PIPELINE = "remove_silences_and_extract_clean_voice"
_DEFAULT_CONFIG = Path(__file__).with_suffix(".yaml")


# ---------------------------------------------------------------------------
# Output path helpers
# ---------------------------------------------------------------------------


def _resolve_video_output(video: Path, suffix: str, output_dir: Path | None = None) -> Path:
    """Return the silence-trimmed video path for a source file."""
    parent = output_dir if output_dir else video.parent
    return safe_output_path(video, parent / f"{video.stem}{suffix}{video.suffix}")


def _resolve_audio_output(
    video_output: Path, suffix: str, *, input_file: Path | None = None
) -> Path:
    """Return the cleaned audio path associated with a trimmed video file."""
    out = video_output.with_name(f"{video_output.stem}{suffix}.wav")
    if input_file:
        safe_output_path(input_file, out)
    return out


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run(
    input_path: str,
    *,
    output_dir: str | None = None,
    output_path: str | None = None,  # ignored — pipeline produces multiple outputs
    force: bool = False,
    config_path: Path | None = None,
    options: dict | None = None,
) -> dict:
    """Process a single video file. Returns result dict."""

    # ── 1. Config ─────────────────────────────────────────────────────────
    cfg = load_config(_DEFAULT_CONFIG, config_path, options)
    verbose = cfg.get("verbose", True)
    video_exts = {e.lower() for e in cfg.get("video_extensions", [".mp4", ".mov", ".mkv"])}
    output_cfg = cfg.get("output", {})
    video_suffix = output_cfg.get("video_suffix", ".silences_removed")
    audio_suffix = output_cfg.get("audio_suffix", ".cleaned_voice")
    propagate_verbose(cfg)
    stage_opts = cfg.get("stages", {})

    # ── 2. Validate input ─────────────────────────────────────────────────
    video = Path(input_path)
    if not video.exists():
        raise FileNotFoundError(f"Input not found: {video}")
    if video.suffix.lower() not in video_exts:
        raise ValueError(f"Not a recognised video file: {video}")

    # ── 3. Resolve all output paths ───────────────────────────────────────
    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    output_video = _resolve_video_output(video, video_suffix, out_dir)
    output_audio = _resolve_audio_output(output_video, audio_suffix, input_file=video)
    temp_sanitized = output_video.parent / f".~sanitize_video~{video.name}"

    # ── 4. Skip check ────────────────────────────────────────────────────
    existing_outputs = [o for o in (output_video, output_audio) if o.exists()]
    if existing_outputs and not force:
        if verbose:
            names = ", ".join(o.name for o in existing_outputs)
            pipeline_log(_PIPELINE, f"[dim]skip[/] {video.name} — output exists: {names}")
        return {
            "skipped": True,
            "input_path": str(video),
            "output_video_path": str(output_video),
            "output_audio_path": str(output_audio),
        }

    if force:
        for existing in (output_video, output_audio):
            if existing.exists():
                existing.unlink()
        if temp_sanitized.exists():
            temp_sanitized.unlink()

    # ── 5. Execute stages ─────────────────────────────────────────────────
    try:
        with pipeline_timer(_PIPELINE, video.name, verbose) as pt:
            sanitize_result = sanitize_video.run(
                str(video),
                str(temp_sanitized),
                options=stage_opts.get("sanitize"),
            )
            remove_result = remove_silences.run(
                str(temp_sanitized), str(output_video), options=stage_opts.get("remove")
            )
            clean_result = extract_and_clean_voice.run(
                str(output_video),
                str(output_audio),
                options={
                    "extract": stage_opts.get("extract", {}),
                    "clean": stage_opts.get("clean", {}),
                    "verbose": verbose,
                },
            )
            pt["output"] = f"{output_video.name} + {output_audio.name}"
    finally:
        if temp_sanitized.exists():
            temp_sanitized.unlink()

    return {
        "input_path": str(video),
        "output_video_path": str(output_video),
        "output_audio_path": str(output_audio),
        "sanitize_result": sanitize_result,
        "remove_result": remove_result,
        "clean_result": clean_result,
    }
