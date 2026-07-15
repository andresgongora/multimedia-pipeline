"""Shared output formatting helpers for stages and pipelines.

Provides consistent terminal output style:
  - stages: dim labels, indented
  - pipelines: bold labels
  - progress lines: yellow wait/work icon (◷)
  - stage_header: log input/output paths and optional config
  - stage_timer: context manager that logs elapsed time on completion
  - pipeline_timer: context manager for timing entire pipeline runs

Stage logging pattern:
    if verbose:
        stage_header(_STAGE, src, dst, {"mode": mode})
    with stage_timer(_STAGE, "done"):
        do_work()

    Output:
      my_stage               → ◷ input.mp4 → output.mp4
      my_stage               → ◷ mode=precise
      my_stage               → ✓ done (12.3s)

Pipeline logging pattern:
    with pipeline_timer(_PIPELINE, src.name, verbose) as pt:
        # stages run here (they log themselves)
        pt["output"] = final.name
    # prints start and done automatically

    Output:
    my_pipeline            → ◷ video.mp4
    my_pipeline            → ✓ video_clean.mp4 (45.2s)
"""

from __future__ import annotations

import re
import time
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console

_console = Console(highlight=False)
_LABEL_WIDTH = 22
_PROGRESS_ICON = "[yellow]◷[/]"
_DECORATED_PREFIX_RE = re.compile(
    r"^(?:\[(?:[^[\]]+)\])*(?:✓|✗|!|\?|skip|◷|⚙|⏳|⌛|•)",
    re.IGNORECASE,
)


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds as a compact human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds) // 60
    secs = seconds - minutes * 60
    return f"{minutes}m{secs:04.1f}s"


def _decorate_message(message: str) -> str:
    """Prefix undecorated messages with a progress icon for alignment."""
    if _DECORATED_PREFIX_RE.match(message):
        return message
    return f"{_PROGRESS_ICON} {message}"


def _path_name(p: str | Path) -> str:
    """Extract filename from path for logging."""
    return Path(p).name if p else ""


def stage_log(stage_name: str, message: str) -> None:
    """Print a stage-level message (dim label)."""
    padded = stage_name.ljust(_LABEL_WIDTH)
    _console.print(f"  [dim]{padded}[/] → {_decorate_message(message)}")


def pipeline_log(pipeline_name: str, message: str) -> None:
    """Print a pipeline-level message (bold label)."""
    padded = pipeline_name.ljust(_LABEL_WIDTH)
    _console.print(f"[bold]{padded}[/] → {_decorate_message(message)}")


def stage_header(
    stage_name: str,
    input_path: str | Path,
    output_path: str | Path | None = None,
    config: dict | None = None,
) -> None:
    """Log stage start with input/output and optional config.

    Usage:
        stage_header("cut", "input.mp4", "output.mp4", {"mode": "precise"})

    Output:
      cut                    → ◷ input.mp4 → output.mp4
      cut                    → ◷ mode=precise
    """
    in_name = _path_name(input_path)
    if output_path:
        out_name = _path_name(output_path)
        stage_log(stage_name, f"[cyan]{in_name}[/] [dim]→[/] [cyan]{out_name}[/]")
    else:
        stage_log(stage_name, f"[cyan]{in_name}[/]")

    if config:
        # Format config as key=value pairs, skip verbose key
        pairs = [f"{k}={v}" for k, v in config.items() if k != "verbose" and v is not None]
        if pairs:
            stage_log(stage_name, f"[dim]{', '.join(pairs)}[/]")


@contextmanager
def stage_timer(stage_name: str, label: str | None = None):
    """Context manager that times a block and logs elapsed time on exit.

    Usage:
        with stage_timer("my_stage", "processing audio"):
            do_work()
        # prints: my_stage → ✓ processing audio (12.3s)

    Yields a dict that the caller can populate with extra info:
        with stage_timer("my_stage") as ctx:
            ctx["detail"] = "42 segments"
        # prints: my_stage → ✓ 42 segments (12.3s)
    """
    ctx: dict = {}
    start = time.monotonic()
    try:
        yield ctx
    finally:
        elapsed = time.monotonic() - start
        detail = ctx.get("detail", label or "done")
        elapsed_str = f"[dim]({_format_elapsed(elapsed)})[/]"
        stage_log(stage_name, f"[green]✓[/] {detail} {elapsed_str}")


@contextmanager
def pipeline_timer(pipeline_name: str, input_name: str, verbose: bool = True):
    """Context manager for timing entire pipeline runs.

    Logs start message, yields context dict, logs completion with elapsed time.
    Set ctx["output"] to customize the done message filename.
    Set ctx["skipped"] = True to suppress done message.

    Usage:
        with pipeline_timer("my_pipeline", src.name, verbose) as pt:
            result = do_pipeline_work()
            pt["output"] = result["output_path"]

    Output:
    my_pipeline            → ◷ input.mp4
    my_pipeline            → ✓ output.mp4 (45.2s)
    """
    ctx: dict = {"output": input_name}
    start = time.monotonic()
    if verbose:
        pipeline_log(pipeline_name, f"[cyan]{input_name}[/]")
    try:
        yield ctx
    finally:
        if verbose and not ctx.get("skipped"):
            elapsed = time.monotonic() - start
            output = _path_name(ctx.get("output", input_name))
            elapsed_str = f"[dim]({_format_elapsed(elapsed)})[/]"
            pipeline_log(pipeline_name, f"[green]✓[/] {output} {elapsed_str}")
