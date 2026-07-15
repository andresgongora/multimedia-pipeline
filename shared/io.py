"""Shared I/O resolution for pipelines.

Centralises input/output path resolution, file discovery, directory
expansion, and the sacred rule: **never overwrite the input file**.

Use :func:`resolve_io` to turn the user's ``input``/``-o`` into a list
of :class:`IOPair` objects ready for the pipeline's ``run()``.

I/O matrix
----------

======  ======  ============================================================
input   output  behaviour
======  ======  ============================================================
file    —       output next to input; pipeline chooses name
file    file    output at exact path; tmp files in its directory
file    dir     output inside directory; pipeline chooses name
dir     —       each output next to its source
dir     dir     outputs in directory (``-r`` mirrors folder tree)
dir     file    **error**
======  ======  ============================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class IOPair(NamedTuple):
    """Resolved I/O mapping for a single file.

    Attributes:
        input_file:  Absolute path to the source file.
        output_dir:  Directory for output and temporary files — always the
                     same directory where the eventual output will land.
        output_file: Explicit output path when the user specified a file
                     for ``-o``.  ``None`` when the pipeline determines
                     the output filename itself.
    """

    input_file: Path
    output_dir: Path
    output_file: Path | None = None


class InputOverwriteError(ValueError):
    """Raised when a proposed output would overwrite the input file."""


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def safe_output_path(input_path: Path | str, output_path: Path | str) -> Path:
    """Validate that *output_path* does not collide with *input_path*.

    Returns *output_path* (as a ``Path``) so it can be used inline::

        out = safe_output_path(src, src.with_suffix(".wav"))

    Raises :class:`InputOverwriteError` if the two paths resolve to the
    same filesystem location.
    """
    inp = Path(input_path).resolve()
    out = Path(output_path).resolve()
    if inp == out:
        raise InputOverwriteError(
            f"Output would overwrite input: {input_path}\n"
            "  Choose a different output path, name, or directory."
        )
    return Path(output_path)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _looks_like_file(p: Path) -> bool:
    """Heuristic: does *p* look like a filename (has a suffix)?"""
    return bool(p.suffix)


def resolve_io(
    input_path: Path | str,
    output: Path | str | None = None,
    *,
    recursive: bool = False,
    extensions: set[str],
) -> list[IOPair]:
    """Resolve input/output pairs for a pipeline invocation.

    Args:
        input_path: File or directory supplied by the user.
        output:     Optional ``-o`` value (file, directory, or ``None``).
        recursive:  When *input_path* is a directory, recurse into
                    subdirectories.
        extensions: Lowercase extensions (including the dot) that qualify
                    as candidate input files when scanning a directory.

    Returns:
        A list of :class:`IOPair` — one per input file found.

    When ``IOPair.output_file`` is ``None``, the pipeline **must** call
    :func:`safe_output_path` before writing to ensure the sacred-input
    invariant holds.
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    # ── Single file ────────────────────────────────────────────────────
    if input_path.is_file():
        if output is None:
            return [IOPair(input_path.resolve(), input_path.resolve().parent)]

        output = Path(output)

        # Existing directory or looks-like-directory → place output inside
        if output.is_dir() or (not output.exists() and not _looks_like_file(output)):
            output.mkdir(parents=True, exist_ok=True)
            return [IOPair(input_path.resolve(), output.resolve())]

        # Treat as explicit output file
        output.parent.mkdir(parents=True, exist_ok=True)
        safe_output_path(input_path, output)
        return [IOPair(input_path.resolve(), output.resolve().parent, output.resolve())]

    # ── Directory ──────────────────────────────────────────────────────
    if input_path.is_dir():
        if output is not None:
            output = Path(output)
            if output.exists() and output.is_file():
                raise ValueError(f"Output cannot be a file when input is a directory: {output}")
            if not output.exists() and _looks_like_file(output):
                raise ValueError(f"Output cannot be a file when input is a directory: {output}")

        glob_iter = input_path.rglob("*") if recursive else input_path.iterdir()
        files = sorted(p for p in glob_iter if p.is_file() and p.suffix.lower() in extensions)

        pairs: list[IOPair] = []
        for f in files:
            if output is None:
                pairs.append(IOPair(f.resolve(), f.resolve().parent))
            else:
                if recursive:
                    rel = f.parent.relative_to(input_path)
                    out_dir = output / rel
                else:
                    out_dir = output
                out_dir.mkdir(parents=True, exist_ok=True)
                pairs.append(IOPair(f.resolve(), out_dir.resolve()))

        return pairs

    raise FileNotFoundError(f"Input not found: {input_path}")
