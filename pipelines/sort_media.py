"""Pipeline: sort_media — move media into configured destination folders.

Given a directory of media files and a YAML rules file:
  1. Parse ``Artist - Title`` filenames.
  2. Match configured artists first, then title keywords.
  3. Move matching files into folders below the output directory.

The input directory is scanned non-recursively. Unknown, malformed, hidden,
and unsupported files are left untouched. Destination collisions fail without
``force=True``; forced runs replace existing files.

Inputs:
    input_dir — directory containing media files.
    config_path — YAML file with ``authors`` and ``keywords`` mappings.
    output_dir — optional destination root; defaults to the parent of input_dir.

Returns:
    Aggregate result containing ``results`` and ``failed``.

Options:
    verbose — print pipeline progress (default: true).

Example:
    ``uv run multimedia-pipeline sort-media /path/to/input -c sort.yaml``
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from shared.output import pipeline_log

_PIPELINE = "sort_media"
_MEDIA_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".mov",
        ".mkv",
        ".avi",
        ".mts",
        ".m2ts",
        ".webm",
        ".m4v",
        ".m4a",
        ".mp3",
        ".opus",
        ".flac",
        ".wav",
        ".ogg",
        ".aac",
        ".mka",
    }
)


class ConfigurationError(ValueError):
    """Raised when sorter configuration is malformed or unsafe."""


class DestinationCollisionError(FileExistsError):
    """Raised when a destination exists and force is disabled."""


@dataclass(frozen=True)
class SortRules:
    """Resolved artist and keyword destinations."""

    author_destinations: dict[str, Path]
    keyword_destinations: dict[str, Path]


def _destination_path(folder: Any, output_root: Path) -> Path:
    if not isinstance(folder, str) or not folder.strip():
        raise ConfigurationError("Destination folders must be non-empty strings.")

    destination = (output_root / folder).resolve()
    if not destination.is_relative_to(output_root) or destination == output_root:
        raise ConfigurationError(f"Destination must be below output root: {folder!r}")
    return destination


def _load_destinations(
    groups: Any,
    section_name: str,
    match_name: str,
    output_root: Path,
) -> dict[str, Path]:
    if not isinstance(groups, dict):
        raise ConfigurationError(f"'{section_name}' must map folders to lists of matches.")

    destinations: dict[str, Path] = {}
    normalized_matches: set[str] = set()
    for folder, matches in groups.items():
        destination = _destination_path(folder, output_root)
        if not isinstance(matches, list):
            raise ConfigurationError(f"'{section_name}' folder entries must be lists.")
        for match in matches:
            if not isinstance(match, str) or not match.strip():
                raise ConfigurationError(f"{match_name} must be non-empty strings.")
            normalized = match.casefold()
            if normalized in normalized_matches:
                raise ConfigurationError(f"Duplicate {section_name} match: {match!r}")
            normalized_matches.add(normalized)
            destinations[match] = destination
    return destinations


def load_sort_rules(config_path: Path, output_root: Path) -> SortRules:
    """Load and validate sorter rules from *config_path*."""
    try:
        document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigurationError(f"Cannot read configuration: {config_path}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid YAML: {config_path}") from error

    if not isinstance(document, dict) or set(document) != {"authors", "keywords"}:
        raise ConfigurationError("Configuration must contain only 'authors' and 'keywords'.")

    return SortRules(
        author_destinations=_load_destinations(
            document["authors"], "authors", "Author names", output_root
        ),
        keyword_destinations=_load_destinations(
            document["keywords"], "keywords", "Keyword matches", output_root
        ),
    )


def _parse_filename(path: Path) -> tuple[str, str] | None:
    if path.suffix.lower() not in _MEDIA_EXTENSIONS:
        return None
    author, separator, title = path.stem.partition(" - ")
    if not separator or not author.strip() or not title.strip():
        return None
    return author, title


def _normalize_keyword_text(text: str) -> str:
    return text.casefold().replace("⁄", "/").replace("∕", "/")


def _keyword_destination(title: str, rules: dict[str, Path]) -> Path | None:
    normalized_title = _normalize_keyword_text(title)
    for keyword, destination in rules.items():
        normalized_keyword = _normalize_keyword_text(keyword)
        pattern = rf"(?<!\w){re.escape(normalized_keyword)}(?!\w)"
        if re.search(pattern, normalized_title):
            return destination
    return None


def _destination_for(path: Path, rules: SortRules) -> Path | None:
    parsed = _parse_filename(path)
    if parsed is None:
        return None
    author, title = parsed
    destination = rules.author_destinations.get(author)
    if destination is not None:
        return destination
    return _keyword_destination(title, rules.keyword_destinations)


def _move(source: Path, destination: Path, *, force: bool) -> None:
    if source == destination:
        raise DestinationCollisionError("Source and destination are the same path")

    if destination.exists() or destination.is_symlink():
        if not force:
            raise DestinationCollisionError(f"Destination already exists: {destination}")
        if destination.is_dir() and not destination.is_symlink():
            raise DestinationCollisionError(f"Destination is a directory: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".~{_PIPELINE}~{destination.name}")
    if temporary.exists() or temporary.is_symlink():
        raise DestinationCollisionError(f"Temporary destination already exists: {temporary}")

    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
        source.unlink()
    finally:
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def run(
    input_dir: str,
    *,
    output_dir: str | None = None,
    force: bool = False,
    config_path: Path | None = None,
    options: dict | None = None,
) -> dict:
    """Sort matching media files from *input_dir* into configured folders."""
    if config_path is None:
        raise ConfigurationError("sort_media requires a YAML config path.")

    source_root = Path(input_dir).expanduser().resolve()
    if not source_root.is_dir():
        raise NotADirectoryError(f"Input is not a directory: {source_root}")

    destination_root = (
        Path(output_dir).expanduser().resolve() if output_dir else source_root.parent
    )
    opts = options or {}
    verbose = bool(opts.get("verbose", True))
    rules = load_sort_rules(Path(config_path).expanduser().resolve(), destination_root)
    files = sorted(
        path
        for path in source_root.iterdir()
        if path.is_file()
        and not path.is_symlink()
        and not path.name.startswith(".")
        and path.suffix.lower() in _MEDIA_EXTENSIONS
    )

    results: list[dict] = []
    processed = 0
    skipped = 0
    failed = 0

    if verbose:
        pipeline_log(_PIPELINE, f"[cyan]{source_root}[/] ({len(files)} candidate file(s))")

    for path in files:
        destination_folder = _destination_for(path, rules)
        if destination_folder is None:
            skipped += 1
            results.append({"input_path": str(path), "status": "unmatched"})
            continue

        destination = destination_folder / path.name
        try:
            _move(path, destination, force=force)
        except Exception as error:
            failed += 1
            results.append(
                {
                    "input_path": str(path),
                    "destination_path": str(destination),
                    "status": "failed",
                    "reason": str(error),
                }
            )
            continue

        processed += 1
        results.append(
            {
                "input_path": str(path),
                "destination_path": str(destination),
                "status": "moved",
            }
        )

    if verbose:
        pipeline_log(
            _PIPELINE,
            f"[green]✓[/] {processed} moved, {skipped} unmatched, {failed} failed",
        )

    return {
        "input_dir": str(source_root),
        "output_dir": str(destination_root),
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Sort media files into configured folders.")
    parser.add_argument("input_dir")
    parser.add_argument("--output", dest="output_dir", default=None)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.input_dir,
                output_dir=args.output_dir,
                force=args.force,
                config_path=args.config,
            ),
            indent=2,
        )
    )
