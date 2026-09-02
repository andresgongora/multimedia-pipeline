"""Shared batch-over-directory runner for batch pipelines.

Centralizes the discover-files / call-per-file-pipeline / aggregate-results
loop shared by every batch pipeline (see AGENTS.md "Pipeline contracts").
Batch pipelines stay thin: load their own config, then delegate to
`run_dir_batch` with the underlying file pipeline's `run()`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from shared.output import pipeline_log


def run_dir_batch(
    pipeline_name: str,
    run_one: Callable[..., dict],
    input_dir: str,
    output_dir: str,
    extensions: set[str],
    *,
    force: bool = False,
    pipeline_options: dict | None = None,
    verbose: bool = True,
) -> dict:
    """Run a file pipeline's `run_one` over every matching file in input_dir.

    `run_one` must follow the file-pipeline contract:
    `run(input_path, *, output_dir=..., force=..., options=...) -> dict`,
    returning `{"skipped": bool, "output_path": str, ...}`. Only files
    directly inside `input_dir` are considered (non-recursive). One file's
    failure does not stop the batch.

    Returns `{"input_dir", "output_dir", "processed", "skipped", "failed",
    "results": list[dict]}`.

    Raises:
        NotADirectoryError: if input_dir is not an existing directory.
    """
    in_dir = Path(input_dir)
    if not in_dir.is_dir():
        raise NotADirectoryError(f"Input is not a directory: {in_dir}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() in extensions)

    results: list[dict] = []
    processed = 0
    skipped = 0
    failed = 0

    start = time.monotonic()
    if verbose:
        pipeline_log(pipeline_name, f"[cyan]{in_dir}[/] ({len(files)} candidate file(s))")

    for i, f in enumerate(files, 1):
        count = f"[{i}/{len(files)}] "
        try:
            result = run_one(str(f), output_dir=str(out_dir), force=force, options=pipeline_options)
            if result.get("skipped"):
                skipped += 1
                status = "skipped"
            else:
                processed += 1
                status = "processed"
            results.append({"input_path": str(f), "status": status, "output_path": result.get("output_path")})
            if verbose:
                icon = "[dim]skip[/]" if status == "skipped" else "[green]\u2713[/]"
                pipeline_log(pipeline_name, f"{count}{icon} {f.name}")
        except Exception as exc:
            failed += 1
            results.append({"input_path": str(f), "status": "failed", "reason": str(exc)})
            if verbose:
                pipeline_log(pipeline_name, f"{count}[red]\u2717[/] {f.name}: {exc}")

    if verbose:
        elapsed = time.monotonic() - start
        pipeline_log(
            pipeline_name,
            f"[green]\u2713[/] {processed} processed, {skipped} skipped, "
            f"{failed} failed ({elapsed:.1f}s)",
        )

    return {
        "input_dir": str(in_dir),
        "output_dir": str(out_dir),
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }
