"""Tests: pipelines/download_youtube_media.py — dedup, error skip, existing-file skip.

Mocks stages.fetch_youtube_playlist and stages.download_youtube_media (no
network). Uses shared.download_registry directly against a temp JSON file.

Usage:
    uv run test/pipelines/download_youtube_media.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines import download_youtube_media as pipeline  # noqa: E402

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


_URLS = [
    "https://www.youtube.com/watch?v=aaaaaaaaaaa",
    "https://www.youtube.com/watch?v=bbbbbbbbbbb",
]


def _fake_fetch(urls: list[str]):
    def fetch(playlist_url: str, options: dict | None = None) -> dict:
        return {"playlist_url": playlist_url, "video_urls": urls, "count": len(urls)}

    return fetch


def _fake_download_ok(video_id: str) -> str:
    return f"Title {video_id}"


def test_invalid_media_type() -> None:
    print("\n--- test_invalid_media_type ---")
    try:
        pipeline.run("https://playlist", "/tmp/out", "/tmp/db.json", "podcast")
        check("raises ValueError", False, "no exception")
    except ValueError:
        check("raises ValueError", True)


def test_download_all_new_and_records_db() -> None:
    print("\n--- test_download_all_new_and_records_db ---")

    def fake_download(url: str, output_path: str, *, options: dict | None = None) -> dict:
        Path(output_path).write_text("data")
        vid = url.rsplit("v=", 1)[1]
        return {
            "output_path": output_path,
            "media_type": options.get("media_type") if options else None,
            "format": "x",
            "remuxed": False,
            "title": _fake_download_ok(vid),
        }

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        db = Path(d) / "db.json"
        with (
            patch.object(pipeline.fetch_youtube_playlist, "run", _fake_fetch(_URLS)),
            patch.object(pipeline.download_youtube_media, "run", fake_download),
        ):
            result = pipeline.run(
                "https://playlist", str(out_dir), str(db), "video", options={"verbose": False}
            )

        check("2 requested", result["requested"] == 2, str(result))
        check("2 downloaded", result["downloaded"] == 2, str(result))
        check("0 failed", result["failed"] == 0, str(result))
        files = sorted(p.name for p in out_dir.iterdir())
        check(
            "filenames use title+bracketed id",
            files == ["Title aaaaaaaaaaa [aaaaaaaaaaa].mkv", "Title bbbbbbbbbbb [bbbbbbbbbbb].mkv"],
            str(files),
        )
        db_data = json.loads(db.read_text())
        check("both urls recorded in db", set(db_data) == set(_URLS), str(db_data))


def test_second_run_skips_known_urls() -> None:
    print("\n--- test_second_run_skips_known_urls ---")
    call_count = {"n": 0}

    def fake_download(url: str, output_path: str, *, options: dict | None = None) -> dict:
        call_count["n"] += 1
        Path(output_path).write_text("data")
        vid = url.rsplit("v=", 1)[1]
        return {
            "output_path": output_path,
            "media_type": None,
            "format": "x",
            "remuxed": False,
            "title": _fake_download_ok(vid),
        }

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        db = Path(d) / "db.json"
        with (
            patch.object(pipeline.fetch_youtube_playlist, "run", _fake_fetch(_URLS)),
            patch.object(pipeline.download_youtube_media, "run", fake_download),
        ):
            pipeline.run("https://playlist", str(out_dir), str(db), "video", options={"verbose": False})
            first_calls = call_count["n"]
            result2 = pipeline.run(
                "https://playlist", str(out_dir), str(db), "video", options={"verbose": False}
            )

        check("first run made 2 download calls", first_calls == 2, str(first_calls))
        check("second run made no new download calls", call_count["n"] == first_calls, str(call_count["n"]))
        check("second run: 0 new", result2["new"] == 0, str(result2))
        check("second run: 2 skipped_known", result2["skipped_known"] == 2, str(result2))


def test_failed_download_not_recorded_and_others_continue() -> None:
    print("\n--- test_failed_download_not_recorded_and_others_continue ---")

    def fake_download(url: str, output_path: str, *, options: dict | None = None) -> dict:
        if "bbbbbbbbbbb" in url:
            raise RuntimeError("simulated yt-dlp failure")
        Path(output_path).write_text("data")
        return {
            "output_path": output_path,
            "media_type": None,
            "format": "x",
            "remuxed": False,
            "title": "Title A",
        }

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        db = Path(d) / "db.json"
        with (
            patch.object(pipeline.fetch_youtube_playlist, "run", _fake_fetch(_URLS)),
            patch.object(pipeline.download_youtube_media, "run", fake_download),
        ):
            result = pipeline.run(
                "https://playlist", str(out_dir), str(db), "video", options={"verbose": False}
            )

        check("1 downloaded, 1 failed", result["downloaded"] == 1 and result["failed"] == 1, str(result))
        db_data = json.loads(db.read_text()) if db.exists() else {}
        check("failed url not recorded", "https://www.youtube.com/watch?v=bbbbbbbbbbb" not in db_data)
        check("succeeded url recorded", "https://www.youtube.com/watch?v=aaaaaaaaaaa" in db_data)


def test_existing_file_on_disk_is_skipped_not_overwritten() -> None:
    print("\n--- test_existing_file_on_disk_is_skipped_not_overwritten ---")
    called = {"n": 0}

    def fake_download(url: str, output_path: str, *, options: dict | None = None) -> dict:
        called["n"] += 1
        Path(output_path).write_text("data")
        return {
            "output_path": output_path,
            "media_type": None,
            "format": "x",
            "remuxed": False,
            "title": "New Title",
        }

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        out_dir.mkdir()
        db = Path(d) / "db.json"
        existing = out_dir / "Old Name [ccccccccccc].mkv"
        existing.write_text("pre-existing content")

        with (
            patch.object(
                pipeline.fetch_youtube_playlist,
                "run",
                _fake_fetch(["https://www.youtube.com/watch?v=ccccccccccc"]),
            ),
            patch.object(pipeline.download_youtube_media, "run", fake_download),
        ):
            result = pipeline.run(
                "https://playlist", str(out_dir), str(db), "video", options={"verbose": False}
            )

        check("download stage not called", called["n"] == 0)
        check("1 skipped_existing", result["skipped_existing"] == 1, str(result))
        check("file untouched", existing.read_text() == "pre-existing content")
        db_data = json.loads(db.read_text()) if db.exists() else {}
        check("not recorded in db", "https://www.youtube.com/watch?v=ccccccccccc" not in db_data)


if __name__ == "__main__":
    test_invalid_media_type()
    test_download_all_new_and_records_db()
    test_second_run_skips_known_urls()
    test_failed_download_not_recorded_and_others_continue()
    test_existing_file_on_disk_is_skipped_not_overwritten()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
