"""Top-level CLI for multimedia-pipeline.

Folder expansion lives in shared.io.  Each pipeline run() accepts exactly one
file.  The CLI resolves directories to file lists and calls the pipeline per file.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from click import Choice

from shared.io import IOPair, resolve_io

app = typer.Typer(
    name="multimedia-pipeline",
    help="Hierarchical stage-based multimedia processing pipeline.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

# ---------------------------------------------------------------------------
# Extension sets
# ---------------------------------------------------------------------------

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".webm"}
_AUDIO_EXTS = {".m4a", ".mp3", ".opus", ".flac", ".wav", ".ogg", ".aac", ".mka"}
_MEDIA_EXTS = _VIDEO_EXTS | _AUDIO_EXTS


# ---------------------------------------------------------------------------
# Common argument types
# ---------------------------------------------------------------------------

InputArg = Annotated[Path, typer.Argument(help="Input file or directory.")]
OutputOpt = Annotated[Path | None, typer.Option("-o", "--output", help="Output file or directory.")]
RecursiveOpt = Annotated[
    bool, typer.Option("-r", "--recursive", help="Recurse into subdirectories.")
]
ForceOpt = Annotated[bool, typer.Option("-f", "--force", help="Overwrite existing outputs.")]
ConfigOpt = Annotated[Path | None, typer.Option("-c", "--config", help="Custom YAML config.")]
QuietOpt = Annotated[bool, typer.Option("-q", "--quiet", help="Suppress progress output.")]
OptionsOpt = Annotated[str | None, typer.Option(help="JSON dict of pipeline/stage overrides.")]


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------


def _run_batch(pairs: list[IOPair], run_one: Callable[[IOPair], None], label: str) -> None:
    """Call run_one(pair) for each IOPair, printing per-file progress."""
    from shared.output import pipeline_log

    errors = 0
    for i, pair in enumerate(pairs, 1):
        count = f"[{i}/{len(pairs)}] " if len(pairs) > 1 else ""
        pipeline_log(label, f"{count}[cyan]{pair.input_file.name}[/]")
        try:
            run_one(pair)
        except Exception as exc:
            pipeline_log(label, f"[red]✗[/] {pair.input_file.name}: {exc}")
            errors += 1
    if errors:
        raise typer.Exit(1)


def _run_pipeline(
    pipeline_module: str,
    name: str,
    extensions: set[str],
    no_files_msg: str,
    input: Path,
    output: Path | None,
    recursive: bool,
    force: bool,
    config: Path | None,
    quiet: bool,
    options: str | None,
) -> None:
    """Common pipeline execution logic."""
    import importlib

    run = importlib.import_module(pipeline_module).run

    opts: dict = json.loads(options) if options else {}
    if quiet:
        opts["verbose"] = False

    pairs = resolve_io(input, output, recursive=recursive, extensions=extensions)
    if not pairs:
        typer.echo(no_files_msg)
        raise typer.Exit(0)

    def run_one(pair: IOPair) -> None:
        run(
            str(pair.input_file),
            output_dir=str(pair.output_dir) if pair.output_file is None else None,
            output_path=str(pair.output_file) if pair.output_file else None,
            force=force,
            config_path=config,
            options=opts,
        )

    _run_batch(pairs, run_one, name)


# ---------------------------------------------------------------------------
# extract-and-clean-voice
# ---------------------------------------------------------------------------


@app.command(
    name="extract-and-clean-voice",
    help="Extract and clean voice from video file(s). Output is a WAV next to each source.",
)
def extract_and_clean_voice(
    input: InputArg,
    output: OutputOpt = None,
    recursive: RecursiveOpt = False,
    force: ForceOpt = False,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    _run_pipeline(
        "pipelines.extract_and_clean_voice",
        "extract-and-clean-voice",
        _VIDEO_EXTS,
        "No video files found.",
        input,
        output,
        recursive,
        force,
        config,
        quiet,
        options,
    )


# ---------------------------------------------------------------------------
# remove-silences-and-extract-clean-voice
# ---------------------------------------------------------------------------


@app.command(
    name="remove-silences-and-extract-clean-voice",
    help="Remove silences then write a trimmed video and cleaned WAV next to each source.",
)
def remove_silences_and_extract_clean_voice(
    input: InputArg,
    output: OutputOpt = None,
    recursive: RecursiveOpt = False,
    force: ForceOpt = False,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    _run_pipeline(
        "pipelines.remove_silences_and_extract_clean_voice",
        "remove-silences-and-extract-clean-voice",
        _VIDEO_EXTS,
        "No video files found.",
        input,
        output,
        recursive,
        force,
        config,
        quiet,
        options,
    )


# ---------------------------------------------------------------------------
# scrub-youtube-media
# ---------------------------------------------------------------------------


@app.command(
    name="scrub-youtube-media",
    help=(
        "Identify media on YouTube, remove sponsored segments via SponsorBlock, "
        "scrub privacy metadata, and suggest a clean filename."
    ),
)
def scrub_youtube_media(
    input: InputArg,
    output: OutputOpt = None,
    recursive: RecursiveOpt = False,
    force: ForceOpt = False,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    _run_pipeline(
        "pipelines.scrub_youtube_media",
        "scrub-youtube-media",
        _MEDIA_EXTS,
        "No media files found.",
        input,
        output,
        recursive,
        force,
        config,
        quiet,
        options,
    )


# ---------------------------------------------------------------------------
# scrub-youtube-podcast
# ---------------------------------------------------------------------------


@app.command(
    name="scrub-youtube-podcast",
    help=(
        "Scrub a YouTube podcast audio file: remove sponsored segments, "
        "apply podcast intelligibility filter, and output as M4A."
    ),
)
def scrub_youtube_podcast(
    input: InputArg,
    output: OutputOpt = None,
    recursive: RecursiveOpt = False,
    force: ForceOpt = False,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    _run_pipeline(
        "pipelines.scrub_youtube_podcast",
        "scrub-youtube-podcast",
        _AUDIO_EXTS,
        "No audio files found.",
        input,
        output,
        recursive,
        force,
        config,
        quiet,
        options,
    )


# ---------------------------------------------------------------------------
# download-youtube-media
# ---------------------------------------------------------------------------

PlaylistArg = Annotated[str, typer.Argument(help="Public YouTube playlist URL.")]
OutputDirArg = Annotated[Path, typer.Argument(help="Directory to download into.")]
MediaTypeOpt = Annotated[
    str,
    typer.Option("--type", help="Media type to download.", click_type=Choice(["video", "audio"])),
]
PlaylistMediaTypeOpt = Annotated[
    str,
    typer.Option(
        "--type",
        help="Media type to download.",
        click_type=Choice(["video", "audio", "music"]),
    ),
]
DbOpt = Annotated[
    Path | None,
    typer.Option("--db", help="Download-registry JSON path (optional — omit to skip dedup)."),
]
WorkDirOpt = Annotated[
    Path | None,
    typer.Option(
        "--work-dir",
        help=(
            "Download work directory (optional — default: hidden dir inside output_dir). "
            "Always wiped on completion."
        ),
    ),
]


@app.command(
    name="download-youtube-media",
    help=(
        "Download every new video in a public YouTube playlist, deduplicated "
        "against a download-registry DB. No further processing (chain other "
        "pipelines on the output directory afterward)."
    ),
)
def download_youtube_media_cmd(
    playlist_url: PlaylistArg,
    output_dir: OutputDirArg,
    media_type: MediaTypeOpt,
    db: DbOpt = None,
    force: ForceOpt = False,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    import pipelines.download_youtube_media as pipeline

    opts: dict = json.loads(options) if options else {}
    if quiet:
        opts["verbose"] = False

    try:
        result = pipeline.run(
            playlist_url,
            str(output_dir),
            media_type,
            db_path=str(db) if db else None,
            force=force,
            config_path=config,
            options=opts,
        )
    except Exception as exc:
        typer.echo(f"download-youtube-media failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    if result["failed"]:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# download-youtube-playlist
# ---------------------------------------------------------------------------


@app.command(
    name="download-youtube-playlist",
    help=(
        "Download an entire public YouTube playlist and scrub every file in "
        "one call: video → scrub-youtube-media, audio → scrub-youtube-podcast, "
        "music → filename-only scrub. "
        "Chains download-youtube-media and the matching batch-scrub pipeline."
    ),
)
def download_youtube_playlist_cmd(
    playlist_url: PlaylistArg,
    output_dir: OutputDirArg,
    media_type: PlaylistMediaTypeOpt,
    work_dir: WorkDirOpt = None,
    db: DbOpt = None,
    force: ForceOpt = False,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    import pipelines.download_youtube_playlist as pipeline

    opts: dict = json.loads(options) if options else {}
    if quiet:
        opts["verbose"] = False

    try:
        result = pipeline.run(
            playlist_url,
            str(output_dir),
            media_type,
            work_dir=str(work_dir) if work_dir else None,
            db_path=str(db) if db else None,
            force=force,
            config_path=config,
            options=opts,
        )
    except Exception as exc:
        typer.echo(f"download-youtube-playlist failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    if result["failed"]:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# batch-scrub-youtube-media / batch-scrub-youtube-podcast
# ---------------------------------------------------------------------------

BatchInputDirArg = Annotated[Path, typer.Argument(help="Directory of files to process.")]
BatchOutputDirArg = Annotated[Path, typer.Argument(help="Directory to write results into.")]
SortConfigOpt = Annotated[
    Path,
    typer.Option("-c", "--config", help="YAML sorting rules."),
]
SortOutputDirOpt = Annotated[
    Path | None,
    typer.Option("-o", "--output", help="Destination root (default: input directory parent)."),
]


def _run_batch_pipeline(
    pipeline_module: str,
    name: str,
    input_dir: Path,
    output_dir: Path,
    force: bool,
    config: Path | None,
    quiet: bool,
    options: str | None,
) -> None:
    """Common batch-pipeline execution logic (folder in, folder out)."""
    import importlib

    run = importlib.import_module(pipeline_module).run

    opts: dict = json.loads(options) if options else {}
    if quiet:
        opts["verbose"] = False

    try:
        result = run(
            str(input_dir),
            str(output_dir),
            force=force,
            config_path=config,
            options=opts,
        )
    except Exception as exc:
        typer.echo(f"{name} failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    if result["failed"]:
        raise typer.Exit(1)


@app.command(
    name="batch-scrub-youtube-media",
    help="Run scrub-youtube-media on every eligible media file in a folder.",
)
def batch_scrub_youtube_media_cmd(
    input_dir: BatchInputDirArg,
    output_dir: BatchOutputDirArg,
    force: ForceOpt = False,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    _run_batch_pipeline(
        "pipelines.batch_scrub_youtube_media",
        "batch-scrub-youtube-media",
        input_dir,
        output_dir,
        force,
        config,
        quiet,
        options,
    )


@app.command(
    name="batch-scrub-youtube-podcast",
    help="Run scrub-youtube-podcast on every eligible audio file in a folder.",
)
def batch_scrub_youtube_podcast_cmd(
    input_dir: BatchInputDirArg,
    output_dir: BatchOutputDirArg,
    force: ForceOpt = False,
    config: ConfigOpt = None,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    _run_batch_pipeline(
        "pipelines.batch_scrub_youtube_podcast",
        "batch-scrub-youtube-podcast",
        input_dir,
        output_dir,
        force,
        config,
        quiet,
        options,
    )


# ---------------------------------------------------------------------------
# sort-media
# ---------------------------------------------------------------------------


@app.command(
    name="sort-media",
    help="Move media files into folders selected by YAML artist and keyword rules.",
)
def sort_media_cmd(
    input_dir: BatchInputDirArg,
    config: SortConfigOpt,
    output_dir: SortOutputDirOpt = None,
    force: ForceOpt = False,
    quiet: QuietOpt = False,
    options: OptionsOpt = None,
) -> None:
    import pipelines.sort_media as pipeline

    opts: dict = json.loads(options) if options else {}
    if quiet:
        opts["verbose"] = False

    try:
        result = pipeline.run(
            str(input_dir),
            output_dir=str(output_dir) if output_dir else None,
            force=force,
            config_path=config,
            options=opts,
        )
    except Exception as exc:
        typer.echo(f"sort-media failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    if result["failed"]:
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()
