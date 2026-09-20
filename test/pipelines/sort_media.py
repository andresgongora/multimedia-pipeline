"""Tests: pipelines/sort_media.py — YAML-driven directory sorting.

Usage:
    uv run test/pipelines/sort_media.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines import sort_media as pipeline  # noqa: E402

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def write_config(path: Path, contents: str) -> Path:
    path.write_text(contents, encoding="utf-8")
    return path


def test_default_output_and_author_match() -> None:
    print("\n--- test_default_output_and_author_match ---")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        input_dir = root / "input"
        input_dir.mkdir()
        source = input_dir / "Veritasium - Magnetism.mp4"
        source.write_text("video", encoding="utf-8")
        config = write_config(
            root / "sort.yaml",
            "authors:\n  Explainers:\n    - Veritasium\nkeywords: {}\n",
        )

        result = pipeline.run(str(input_dir), config_path=config, options={"verbose": False})
        destination = root / "Explainers" / source.name

        check("uses input parent as default output", result["output_dir"] == str(root))
        check("moves matching author", result["processed"] == 1)
        check("creates nested destination", destination.exists())
        check("removes source", not source.exists())


def test_author_precedes_keyword_and_unmatched_stays() -> None:
    print("\n--- test_author_precedes_keyword_and_unmatched_stays ---")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        input_dir = root / "input"
        input_dir.mkdir()
        author_match = input_dir / "Veritasium - Magnetism.mp4"
        keyword_match = input_dir / "Unknown - Drone flight.m4a"
        unmatched = input_dir / "Unknown - Magnetism.mp3"
        ignored = input_dir / "notes.txt"
        for path in (author_match, keyword_match, unmatched, ignored):
            path.write_text("media", encoding="utf-8")
        config = write_config(
            root / "sort.yaml",
            """authors:
  Explainers:
    - Veritasium
keywords:
  Drone:
    - drone
""",
        )

        result = pipeline.run(
            str(input_dir),
            output_dir=str(root / "library"),
            config_path=config,
            options={"verbose": False},
        )

        check(
            "author wins over keyword",
            (root / "library/Explainers" / author_match.name).exists(),
        )
        check("keyword matches title", (root / "library/Drone" / keyword_match.name).exists())
        check("unmatched file remains", unmatched.exists())
        check("unsupported file remains", ignored.exists())
        check("one unmatched file is skipped", result["skipped"] == 1)


def test_collision_fails_without_force_and_force_replaces() -> None:
    print("\n--- test_collision_fails_without_force_and_force_replaces ---")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        input_dir = root / "input"
        destination_dir = root / "library" / "Explainers"
        input_dir.mkdir()
        destination_dir.mkdir(parents=True)
        source = input_dir / "Veritasium - Magnetism.mp4"
        destination = destination_dir / source.name
        source.write_text("new", encoding="utf-8")
        destination.write_text("old", encoding="utf-8")
        config = write_config(
            root / "sort.yaml",
            "authors:\n  Explainers:\n    - Veritasium\nkeywords: {}\n",
        )

        result = pipeline.run(
            str(input_dir),
            output_dir=str(root / "library"),
            config_path=config,
            options={"verbose": False},
        )
        check("collision is reported as failure", result["failed"] == 1)
        check("source survives collision", source.read_text(encoding="utf-8") == "new")
        check("destination survives collision", destination.read_text(encoding="utf-8") == "old")

        forced = pipeline.run(
            str(input_dir),
            output_dir=str(root / "library"),
            force=True,
            config_path=config,
            options={"verbose": False},
        )
        check("force moves colliding source", forced["processed"] == 1 and not source.exists())
        check("force replaces destination", destination.read_text(encoding="utf-8") == "new")


def test_rejects_unsafe_destination_and_missing_config() -> None:
    print("\n--- test_rejects_unsafe_destination_and_missing_config ---")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        input_dir = root / "input"
        input_dir.mkdir()
        unsafe = write_config(
            root / "unsafe.yaml",
            "authors:\n  ../outside:\n    - Veritasium\nkeywords: {}\n",
        )

        try:
            pipeline.run(str(input_dir), config_path=unsafe, options={"verbose": False})
        except pipeline.ConfigurationError:
            check("rejects destination outside output root", True)
        else:
            check("rejects destination outside output root", False)

        try:
            pipeline.run(str(input_dir), options={"verbose": False})
        except pipeline.ConfigurationError:
            check("requires config path", True)
        else:
            check("requires config path", False)


def test_rejects_destination_equal_to_source() -> None:
    print("\n--- test_rejects_destination_equal_to_source ---")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        input_dir = root / "input"
        input_dir.mkdir()
        source = input_dir / "Veritasium - Magnetism.mp4"
        source.write_text("video", encoding="utf-8")
        config = write_config(
            root / "sort.yaml",
            "authors:\n  input:\n    - Veritasium\nkeywords: {}\n",
        )

        result = pipeline.run(
            str(input_dir),
            force=True,
            config_path=config,
            options={"verbose": False},
        )

        check("same-path move fails", result["failed"] == 1)
        check("same-path source survives", source.read_text(encoding="utf-8") == "video")


def test_failure_does_not_stop_later_files() -> None:
    print("\n--- test_failure_does_not_stop_later_files ---")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        input_dir = root / "input"
        library = root / "library"
        blocked = library / "Blocked" / "A - One.mp4"
        input_dir.mkdir()
        blocked.parent.mkdir(parents=True)
        blocked.write_text("existing", encoding="utf-8")
        first = input_dir / "A - One.mp4"
        second = input_dir / "Veritasium - Two.mp4"
        first.write_text("first", encoding="utf-8")
        second.write_text("second", encoding="utf-8")
        config = write_config(
            root / "sort.yaml",
            """authors:
  Blocked:
    - A
  Explainers:
    - Veritasium
keywords: {}
""",
        )

        result = pipeline.run(
            str(input_dir),
            output_dir=str(library),
            config_path=config,
            options={"verbose": False},
        )

        check("one file fails", result["failed"] == 1)
        check("later file still moves", result["processed"] == 1)
        check("failed source remains", first.exists())
        check("later destination exists", (library / "Explainers" / second.name).exists())


if __name__ == "__main__":
    test_default_output_and_author_match()
    test_author_precedes_keyword_and_unmatched_stays()
    test_collision_fails_without_force_and_force_replaces()
    test_rejects_unsafe_destination_and_missing_config()
    test_rejects_destination_equal_to_source()
    test_failure_does_not_stop_later_files()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
