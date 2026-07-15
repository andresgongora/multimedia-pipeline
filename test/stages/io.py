"""Tests: shared/io.py — I/O resolution, sacred-input guard, directory expansion.

Usage:
    uv run test/stages/io.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.io import IOPair, InputOverwriteError, resolve_io, safe_output_path

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


EXTS = {".txt", ".wav"}


# ---------------------------------------------------------------------------
# safe_output_path
# ---------------------------------------------------------------------------


def test_safe_output_path_different() -> None:
    print("\n--- test_safe_output_path_different ---")
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "input.txt"
        out = Path(tmp) / "output.txt"
        inp.touch()
        result = safe_output_path(inp, out)
        check("returns output_path", result == out)


def test_safe_output_path_same() -> None:
    print("\n--- test_safe_output_path_same ---")
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "same.txt"
        inp.touch()
        try:
            safe_output_path(inp, inp)
            check("raises InputOverwriteError", False, "no exception")
        except InputOverwriteError:
            check("raises InputOverwriteError", True)


def test_safe_output_path_symlink() -> None:
    """Symlink to input should also be caught."""
    print("\n--- test_safe_output_path_symlink ---")
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "input.txt"
        link = Path(tmp) / "link.txt"
        inp.touch()
        link.symlink_to(inp)
        try:
            safe_output_path(inp, link)
            check("raises for symlink to input", False, "no exception")
        except InputOverwriteError:
            check("raises for symlink to input", True)


# ---------------------------------------------------------------------------
# resolve_io — file input
# ---------------------------------------------------------------------------


def test_file_no_output() -> None:
    """input=file, output=None → output_dir is input's parent."""
    print("\n--- test_file_no_output ---")
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "audio.wav"
        inp.touch()
        pairs = resolve_io(inp, None, extensions=EXTS)
        check("one pair", len(pairs) == 1)
        check("input_file resolved", pairs[0].input_file == inp.resolve())
        check("output_dir is parent", pairs[0].output_dir == inp.resolve().parent)
        check("output_file is None", pairs[0].output_file is None)


def test_file_output_dir() -> None:
    """input=file, output=dir → output_dir is that directory."""
    print("\n--- test_file_output_dir ---")
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "audio.wav"
        out_dir = Path(tmp) / "results"
        inp.touch()
        out_dir.mkdir()
        pairs = resolve_io(inp, out_dir, extensions=EXTS)
        check("one pair", len(pairs) == 1)
        check("output_dir is specified dir", pairs[0].output_dir == out_dir.resolve())
        check("output_file is None", pairs[0].output_file is None)


def test_file_output_new_dir() -> None:
    """input=file, output=non-existent path without suffix → creates dir."""
    print("\n--- test_file_output_new_dir ---")
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "audio.wav"
        out_dir = Path(tmp) / "new_results"
        inp.touch()
        pairs = resolve_io(inp, out_dir, extensions=EXTS)
        check("one pair", len(pairs) == 1)
        check("dir created", out_dir.exists() and out_dir.is_dir())
        check("output_dir is new dir", pairs[0].output_dir == out_dir.resolve())
        check("output_file is None", pairs[0].output_file is None)


def test_file_output_file() -> None:
    """input=file, output=file → explicit output_file set."""
    print("\n--- test_file_output_file ---")
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "audio.wav"
        out = Path(tmp) / "result.wav"
        inp.touch()
        pairs = resolve_io(inp, out, extensions=EXTS)
        check("one pair", len(pairs) == 1)
        check("output_file set", pairs[0].output_file == out.resolve())
        check("output_dir is file's parent", pairs[0].output_dir == out.resolve().parent)


def test_file_output_file_overwrite_input() -> None:
    """input=file, output=same file → raises InputOverwriteError."""
    print("\n--- test_file_output_file_overwrite_input ---")
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "audio.wav"
        inp.touch()
        try:
            resolve_io(inp, inp, extensions=EXTS)
            check("raises InputOverwriteError", False, "no exception")
        except InputOverwriteError:
            check("raises InputOverwriteError", True)


# ---------------------------------------------------------------------------
# resolve_io — directory input
# ---------------------------------------------------------------------------


def test_dir_no_output() -> None:
    """input=dir, output=None → each file's output_dir is its own parent."""
    print("\n--- test_dir_no_output ---")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "media"
        d.mkdir()
        (d / "a.wav").touch()
        (d / "b.txt").touch()
        (d / "c.mp3").touch()  # not in EXTS
        pairs = resolve_io(d, None, extensions=EXTS)
        names = {p.input_file.name for p in pairs}
        check("found a.wav and b.txt", names == {"a.wav", "b.txt"})
        check("skipped c.mp3", "c.mp3" not in names)
        for p in pairs:
            check(f"{p.input_file.name} output_dir is parent", p.output_dir == d.resolve())


def test_dir_output_dir() -> None:
    """input=dir, output=dir → all outputs in specified dir."""
    print("\n--- test_dir_output_dir ---")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "media"
        out = Path(tmp) / "results"
        d.mkdir()
        out.mkdir()
        (d / "a.wav").touch()
        (d / "b.wav").touch()
        pairs = resolve_io(d, out, extensions=EXTS)
        check("two pairs", len(pairs) == 2)
        for p in pairs:
            check(f"{p.input_file.name} output_dir is results/", p.output_dir == out.resolve())


def test_dir_output_file_error() -> None:
    """input=dir, output=file → raises ValueError."""
    print("\n--- test_dir_output_file_error ---")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "media"
        out = Path(tmp) / "result.wav"
        d.mkdir()
        (d / "a.wav").touch()
        out.touch()  # make it a real file
        try:
            resolve_io(d, out, extensions=EXTS)
            check("raises ValueError", False, "no exception")
        except ValueError:
            check("raises ValueError", True)


def test_dir_output_looks_like_file_error() -> None:
    """input=dir, output=non-existent file-looking path → raises ValueError."""
    print("\n--- test_dir_output_looks_like_file_error ---")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "media"
        d.mkdir()
        (d / "a.wav").touch()
        try:
            resolve_io(d, Path(tmp) / "result.wav", extensions=EXTS)
            check("raises ValueError", False, "no exception")
        except ValueError:
            check("raises ValueError", True)


# ---------------------------------------------------------------------------
# resolve_io — recursive
# ---------------------------------------------------------------------------


def test_dir_recursive() -> None:
    """input=dir, recursive=True → finds files in subdirectories."""
    print("\n--- test_dir_recursive ---")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "media"
        sub = d / "sub"
        sub.mkdir(parents=True)
        (d / "a.wav").touch()
        (sub / "b.wav").touch()

        # Without recursive
        pairs_flat = resolve_io(d, None, recursive=False, extensions=EXTS)
        flat_names = {p.input_file.name for p in pairs_flat}
        check("non-recursive finds only top level", flat_names == {"a.wav"})

        # With recursive
        pairs_rec = resolve_io(d, None, recursive=True, extensions=EXTS)
        rec_names = {p.input_file.name for p in pairs_rec}
        check("recursive finds both files", rec_names == {"a.wav", "b.wav"})


def test_dir_recursive_mirror() -> None:
    """input=dir, output=dir, recursive → mirrors folder structure."""
    print("\n--- test_dir_recursive_mirror ---")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "media"
        sub = d / "sub"
        sub.mkdir(parents=True)
        out = Path(tmp) / "results"
        (d / "a.wav").touch()
        (sub / "b.wav").touch()

        pairs = resolve_io(d, out, recursive=True, extensions=EXTS)
        check("two pairs", len(pairs) == 2)

        pair_a = [p for p in pairs if p.input_file.name == "a.wav"][0]
        pair_b = [p for p in pairs if p.input_file.name == "b.wav"][0]
        check("a.wav output_dir is results/", pair_a.output_dir == out.resolve())
        check("b.wav output_dir mirrors sub/", pair_b.output_dir == (out / "sub").resolve())
        check("sub dir created", (out / "sub").is_dir())


# ---------------------------------------------------------------------------
# resolve_io — edge cases
# ---------------------------------------------------------------------------


def test_missing_input() -> None:
    """Non-existent input raises FileNotFoundError."""
    print("\n--- test_missing_input ---")
    try:
        resolve_io(Path("/definitely/nonexistent"), None, extensions=EXTS)
        check("raises FileNotFoundError", False, "no exception")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


def test_empty_dir() -> None:
    """Directory with no matching files returns empty list."""
    print("\n--- test_empty_dir ---")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "empty"
        d.mkdir()
        (d / "readme.md").touch()  # not in EXTS
        pairs = resolve_io(d, None, extensions=EXTS)
        check("empty list", pairs == [])


def test_tmp_dir_equals_output_dir() -> None:
    """Verify that output_dir (where tmp files should go) is always the
    same directory as the eventual output location."""
    print("\n--- test_tmp_dir_equals_output_dir ---")
    with tempfile.TemporaryDirectory() as tmp:
        # file → dir case
        inp = Path(tmp) / "audio.wav"
        out = Path(tmp) / "results"
        inp.touch()
        out.mkdir()
        pairs = resolve_io(inp, out, extensions=EXTS)
        check("tmp_dir for file→dir", pairs[0].output_dir == out.resolve())

        # file → file case
        out_file = Path(tmp) / "results" / "output.wav"
        pairs2 = resolve_io(inp, out_file, extensions=EXTS)
        check(
            "tmp_dir for file→file is file's parent",
            pairs2[0].output_dir == out_file.resolve().parent,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_safe_output_path_different()
    test_safe_output_path_same()
    test_safe_output_path_symlink()
    test_file_no_output()
    test_file_output_dir()
    test_file_output_new_dir()
    test_file_output_file()
    test_file_output_file_overwrite_input()
    test_dir_no_output()
    test_dir_output_dir()
    test_dir_output_file_error()
    test_dir_output_looks_like_file_error()
    test_dir_recursive()
    test_dir_recursive_mirror()
    test_missing_input()
    test_empty_dir()
    test_tmp_dir_equals_output_dir()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
