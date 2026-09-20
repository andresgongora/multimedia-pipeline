"""Tests: pipelines/batch_scrub_youtube_media.py — delegation, aggregation, error isolation.

Mocks pipelines.scrub_youtube_media.run (no network, no real media).

Usage:
    uv run test/pipelines/batch_scrub_youtube_media.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines import batch_scrub_youtube_media as pipeline  # noqa: E402

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


def test_not_a_directory_raises() -> None:
    print("\n--- test_not_a_directory_raises ---")
    with tempfile.TemporaryDirectory() as d:
        missing = Path(d) / "nope"
        try:
            pipeline.run(str(missing), str(Path(d) / "out"))
            check("raises NotADirectoryError", False, "no exception")
        except NotADirectoryError:
            check("raises NotADirectoryError", True)


def test_processes_every_eligible_file() -> None:
    print("\n--- test_processes_every_eligible_file ---")
    with tempfile.TemporaryDirectory() as d:
        in_dir = Path(d) / "in"
        out_dir = Path(d) / "out"
        in_dir.mkdir()
        (in_dir / "a.mp4").write_text("x")
        (in_dir / "b.m4a").write_text("x")
        (in_dir / "c.txt").write_text("ignore me")

        calls: list[str] = []

        def fake_scrub(
            input_path: str, *, output_dir: str, force: bool, options: dict | None
        ) -> dict:
            calls.append(input_path)
            out = str(Path(output_dir) / Path(input_path).name)
            return {"skipped": False, "output_path": out, "identified": False}

        with patch.object(pipeline.scrub_youtube_media, "run", fake_scrub):
            result = pipeline.run(str(in_dir), str(out_dir), force=True, options={"verbose": False})

        check("2 media files delegated (txt ignored)", len(calls) == 2, str(calls))
        check("2 processed", result["processed"] == 2, str(result))
        check("0 failed", result["failed"] == 0, str(result))
        check("input_dir/output_dir echoed", result["input_dir"] == str(in_dir), str(result))


def test_one_failure_does_not_stop_batch() -> None:
    print("\n--- test_one_failure_does_not_stop_batch ---")
    with tempfile.TemporaryDirectory() as d:
        in_dir = Path(d) / "in"
        out_dir = Path(d) / "out"
        in_dir.mkdir()
        (in_dir / "ok.mp4").write_text("x")
        (in_dir / "bad.mp4").write_text("x")

        def fake_scrub(
            input_path: str, *, output_dir: str, force: bool, options: dict | None
        ) -> dict:
            if "bad" in input_path:
                raise RuntimeError("simulated failure")
            return {"skipped": False, "output_path": input_path, "identified": False}

        with patch.object(pipeline.scrub_youtube_media, "run", fake_scrub):
            result = pipeline.run(str(in_dir), str(out_dir), force=True, options={"verbose": False})

        check(
            "1 processed, 1 failed", result["processed"] == 1 and result["failed"] == 1, str(result)
        )


if __name__ == "__main__":
    test_not_a_directory_raises()
    test_processes_every_eligible_file()
    test_one_failure_does_not_stop_batch()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
