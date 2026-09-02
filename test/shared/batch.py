"""Tests: shared/batch.py — run_dir_batch discovery, delegation, aggregation.

No network, no real media — run_one is mocked.

Usage:
    uv run test/shared/batch.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.batch import run_dir_batch  # noqa: E402

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
            run_dir_batch("test", lambda *a, **k: {}, str(missing), str(Path(d) / "out"), {".mp4"})
            check("raises NotADirectoryError", False, "no exception")
        except NotADirectoryError:
            check("raises NotADirectoryError", True)


def test_filters_by_extension_and_delegates() -> None:
    print("\n--- test_filters_by_extension_and_delegates ---")
    with tempfile.TemporaryDirectory() as d:
        in_dir = Path(d) / "in"
        out_dir = Path(d) / "out"
        in_dir.mkdir()
        (in_dir / "a.mp4").write_text("x")
        (in_dir / "b.mp4").write_text("x")
        (in_dir / "c.txt").write_text("ignore me")

        calls: list[str] = []

        def fake_run(input_path: str, *, output_dir: str, force: bool, options: dict | None) -> dict:
            calls.append(input_path)
            return {"skipped": False, "output_path": str(Path(output_dir) / Path(input_path).name)}

        result = run_dir_batch("test", fake_run, str(in_dir), str(out_dir), {".mp4"}, force=True)

        check("only .mp4 files considered", len(calls) == 2, str(calls))
        check("processed count", result["processed"] == 2, str(result))
        check("skipped count", result["skipped"] == 0, str(result))
        check("failed count", result["failed"] == 0, str(result))
        check("results has 2 entries", len(result["results"]) == 2, str(result["results"]))


def test_skip_and_failure_isolated() -> None:
    print("\n--- test_skip_and_failure_isolated ---")
    with tempfile.TemporaryDirectory() as d:
        in_dir = Path(d) / "in"
        out_dir = Path(d) / "out"
        in_dir.mkdir()
        (in_dir / "ok.mp4").write_text("x")
        (in_dir / "skip.mp4").write_text("x")
        (in_dir / "bad.mp4").write_text("x")

        def fake_run(input_path: str, *, output_dir: str, force: bool, options: dict | None) -> dict:
            name = Path(input_path).name
            if name == "skip.mp4":
                return {"skipped": True, "output_path": str(Path(output_dir) / name)}
            if name == "bad.mp4":
                raise RuntimeError("boom")
            return {"skipped": False, "output_path": str(Path(output_dir) / name)}

        result = run_dir_batch("test", fake_run, str(in_dir), str(out_dir), {".mp4"})

        check("1 processed", result["processed"] == 1, str(result))
        check("1 skipped", result["skipped"] == 1, str(result))
        check("1 failed", result["failed"] == 1, str(result))
        statuses = {r["input_path"]: r["status"] for r in result["results"]}
        check(
            "statuses match",
            statuses[str(in_dir / "ok.mp4")] == "processed"
            and statuses[str(in_dir / "skip.mp4")] == "skipped"
            and statuses[str(in_dir / "bad.mp4")] == "failed",
            str(statuses),
        )
        bad_entry = next(r for r in result["results"] if r["input_path"] == str(in_dir / "bad.mp4"))
        check("failed entry carries reason", bad_entry.get("reason") == "boom", str(bad_entry))


if __name__ == "__main__":
    test_not_a_directory_raises()
    test_filters_by_extension_and_delegates()
    test_skip_and_failure_isolated()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
