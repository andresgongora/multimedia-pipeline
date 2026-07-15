"""Quick CLI smoke tests.

Usage:
    uv run test/cli/help.py
"""

from __future__ import annotations

import subprocess
import sys

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


def run_cmd(args: list[str]) -> tuple[int, str]:
    result = subprocess.run(args, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output


def test_top_level_help() -> None:
    print("\n--- test_top_level_help ---")
    code, output = run_cmd(["multimedia-pipeline", "--help"])
    check("exit code is 0", code == 0, f"code={code}")
    check("includes subcommand", "extract-and-clean-voice" in output)
    check("rendered with Rich panels", "╭" in output or "Commands" in output)


def test_pipeline_help() -> None:
    print("\n--- test_pipeline_help ---")
    code, output = run_cmd(["multimedia-pipeline", "extract-and-clean-voice", "--help"])
    check("exit code is 0", code == 0, f"code={code}")
    check("includes --config", "--config" in output)
    check("includes input arg", "input" in output.lower())
    check("shows type hints", "PATH" in output or "TEXT" in output)


def test_remove_silences_pipeline_help() -> None:
    print("\n--- test_remove_silences_pipeline_help ---")
    code, output = run_cmd(
        [
            "multimedia-pipeline",
            "remove-silences-and-extract-clean-voice",
            "--help",
        ]
    )
    check("exit code is 0", code == 0, f"code={code}")
    check("includes --config", "--config" in output)
    check("mentions cleaned wav", "cleaned WAV" in output or "cleaned wav" in output)
    check("includes input arg", "input" in output.lower())


if __name__ == "__main__":
    test_top_level_help()
    test_pipeline_help()
    test_remove_silences_pipeline_help()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
