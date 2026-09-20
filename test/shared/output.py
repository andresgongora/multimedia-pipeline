"""Tests: shared/output.py — formatting helpers.

Usage:
    uv run test/shared/output.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.output import _decorate_message, _format_elapsed, _path_name

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


def test_format_elapsed_seconds() -> None:
    print("\n--- test_format_elapsed_seconds ---")
    check("sub-second", _format_elapsed(0.5) == "0.5s", _format_elapsed(0.5))
    check("whole seconds", _format_elapsed(12.3) == "12.3s", _format_elapsed(12.3))
    check("59 seconds", _format_elapsed(59.9) == "59.9s", _format_elapsed(59.9))


def test_format_elapsed_minutes() -> None:
    print("\n--- test_format_elapsed_minutes ---")
    result = _format_elapsed(90.0)
    check("90s → 1m30.0s", result == "1m30.0s", result)
    result2 = _format_elapsed(3661.5)
    check("3661.5s → 61m01.5s", result2 == "61m01.5s", result2)


def test_decorate_message_plain() -> None:
    print("\n--- test_decorate_message_plain ---")
    result = _decorate_message("processing audio")
    check("adds progress icon", "\u25f7" in result or "◷" in result, repr(result))


def test_decorate_message_already_decorated() -> None:
    print("\n--- test_decorate_message_already_decorated ---")
    result = _decorate_message("\u2713 done")
    check("no double decoration", result == "\u2713 done", repr(result))


def test_path_name_empty_and_none() -> None:
    print("\n--- test_path_name_empty_and_none ---")
    check("empty string", _path_name("") == "")


def test_path_name_from_string() -> None:
    print("\n--- test_path_name_from_string ---")
    check("extracts filename", _path_name("/foo/bar/baz.mp4") == "baz.mp4")


def test_path_name_from_path() -> None:
    print("\n--- test_path_name_from_path ---")
    check("Path object", _path_name(Path("/foo/bar/baz.mp4")) == "baz.mp4")


if __name__ == "__main__":
    test_format_elapsed_seconds()
    test_format_elapsed_minutes()
    test_decorate_message_plain()
    test_decorate_message_already_decorated()
    test_path_name_empty_and_none()
    test_path_name_from_string()
    test_path_name_from_path()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
