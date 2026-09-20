"""Tests: shared/config.py — deep_merge, load_config, propagate_verbose.

Usage:
    uv run test/shared/config.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.config import deep_merge, load_config, propagate_verbose

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


def test_deep_merge_flat() -> None:
    print("\n--- test_deep_merge_flat ---")
    base = {"a": 1, "b": 2}
    override = {"b": 3, "c": 4}
    result = deep_merge(base, override)
    check("override wins", result["b"] == 3)
    check("base kept", result["a"] == 1)
    check("new key added", result["c"] == 4)
    check("base unchanged", base == {"a": 1, "b": 2})


def test_deep_merge_nested() -> None:
    print("\n--- test_deep_merge_nested ---")
    base = {"stages": {"cut": {"mode": "precise", "verbose": True}, "identify": {"search": True}}}
    override = {"stages": {"cut": {"mode": "fast"}}}
    result = deep_merge(base, override)
    check("nested override", result["stages"]["cut"]["mode"] == "fast")
    check("nested base kept", result["stages"]["cut"]["verbose"] is True)
    check("sibling kept", result["stages"]["identify"]["search"] is True)


def test_deep_merge_replaces_non_dict() -> None:
    print("\n--- test_deep_merge_replaces_non_dict ---")
    base = {"x": {"a": 1}}
    override = {"x": "scalar"}
    result = deep_merge(base, override)
    check("dict replaced by scalar", result["x"] == "scalar")


def test_load_config_default_only() -> None:
    print("\n--- test_load_config_default_only ---")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("verbose: true\nstages:\n  cut:\n    mode: precise\n")
        default = Path(f.name)
    try:
        cfg = load_config(default)
        check("verbose loaded", cfg["verbose"] is True)
        check("stage config loaded", cfg["stages"]["cut"]["mode"] == "precise")
    finally:
        default.unlink()


def test_load_config_custom_override() -> None:
    print("\n--- test_load_config_custom_override ---")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("stages:\n  cut:\n    mode: precise\n")
        default = Path(f.name)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("stages:\n  cut:\n    mode: fast\n")
        custom = Path(f.name)
    try:
        cfg = load_config(default, custom)
        check("custom overrides default", cfg["stages"]["cut"]["mode"] == "fast")
    finally:
        default.unlink()
        custom.unlink()


def test_load_config_runtime_overrides() -> None:
    print("\n--- test_load_config_runtime_overrides ---")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("verbose: true\nstages:\n  cut:\n    mode: precise\n")
        default = Path(f.name)
    try:
        cfg = load_config(
            default, overrides={"verbose": False, "stages": {"cut": {"mode": "fast"}}}
        )
        check("runtime override verbose", cfg["verbose"] is False)
        check("runtime override stage", cfg["stages"]["cut"]["mode"] == "fast")
    finally:
        default.unlink()


def test_propagate_verbose() -> None:
    print("\n--- test_propagate_verbose ---")
    cfg = {
        "verbose": False,
        "stages": {
            "cut": {"mode": "precise"},
            "identify": {"search": True, "verbose": True},
            "not_a_dict": "skip",
        },
    }
    propagate_verbose(cfg)
    check("propagated to cut", cfg["stages"]["cut"]["verbose"] is False)
    check("existing verbose kept", cfg["stages"]["identify"]["verbose"] is True)
    check("non-dict skipped", cfg["stages"]["not_a_dict"] == "skip")


def test_propagate_verbose_default_true() -> None:
    print("\n--- test_propagate_verbose_default_true ---")
    cfg = {"stages": {"cut": {}}}
    propagate_verbose(cfg)
    check("defaults to True", cfg["stages"]["cut"]["verbose"] is True)


if __name__ == "__main__":
    test_deep_merge_flat()
    test_deep_merge_nested()
    test_deep_merge_replaces_non_dict()
    test_load_config_default_only()
    test_load_config_custom_override()
    test_load_config_runtime_overrides()
    test_propagate_verbose()
    test_propagate_verbose_default_true()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
