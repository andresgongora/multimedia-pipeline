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
_AUDIO_EXTS = {".m4a", ".mp3", ".opus", ".flac", ".wav", ".ogg", ".aac"}
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

ecv = typer.Typer(
    name="extract-and-clean-voice",
    help="Extract and clean voice from video file(s). Output is a WAV next to each source.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(ecv)


@ecv.callback(invoke_without_command=True)
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

rsecv = typer.Typer(
    name="remove-silences-and-extract-clean-voice",
    help="Remove silences then write a trimmed video and cleaned WAV next to each source.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(rsecv)


@rsecv.callback(invoke_without_command=True)
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

sym = typer.Typer(
    name="scrub-youtube-media",
    help=(
        "Identify media on YouTube, remove sponsored segments via SponsorBlock, "
        "scrub privacy metadata, and suggest a clean filename."
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(sym)


@sym.callback(invoke_without_command=True)
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

syp = typer.Typer(
    name="scrub-youtube-podcast",
    help=(
        "Scrub a YouTube podcast audio file: remove sponsored segments, "
        "apply podcast intelligibility filter, and output as M4A."
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
app.add_typer(syp)


@syp.callback(invoke_without_command=True)
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
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()
