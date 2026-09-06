"""Tests: pipelines/download_youtube_playlist.py — download, scrub, and rescue.

Mocks download and scrub pipelines (no network or ffmpeg).

Usage:
    uv run test/pipelines/download_youtube_playlist.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines import download_youtube_playlist as pipeline  # noqa: E402

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


def test_invalid_media_type() -> None:
    print("\n--- test_invalid_media_type ---")
    try:
        pipeline.run("https://playlist", "/tmp/out", "podcast")
        check("raises ValueError", False, "no exception")
    except ValueError:
        check("raises ValueError", True)


def test_video_happy_path() -> None:
    print("\n--- test_video_happy_path ---")

    def fake_download(_url: str, output_dir: str, _media_type: str, **_kwargs) -> dict:
        results = []
        for index, url in enumerate(_URLS):
            path = Path(output_dir) / f"video-{index}.mkv"
            path.write_text("downloaded")
            results.append({"url": url, "status": "downloaded", "output_path": str(path)})
        return {"downloaded": 2, "failed": 0, "results": results}

    def fake_scrub(_input_dir: str, output_dir: str, **_kwargs) -> dict:
        results = []
        for path in sorted(Path(_input_dir).iterdir()):
            output_path = Path(output_dir) / path.name
            output_path.write_text("scrubbed")
            results.append(
                {"input_path": str(path), "status": "processed", "output_path": str(output_path)}
            )
        return {"processed": 2, "skipped": 0, "failed": 0, "results": results}

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        with (
            patch.object(pipeline.download_youtube_media, "run", fake_download),
            patch.object(pipeline.batch_scrub_youtube_media, "run", fake_scrub),
            patch.object(pipeline.batch_scrub_youtube_podcast, "run") as scrub_podcast,
        ):
            result = pipeline.run(
                "https://playlist", str(out_dir), "video", options={"verbose": False}
            )

        check("2 downloaded", result["downloaded"] == 2, str(result))
        check("2 processed", result["processed"] == 2, str(result))
        check("0 failed", result["failed"] == 0, str(result))
        check("scrubbed files exist", all((out_dir / f"video-{i}.mkv").exists() for i in range(2)))
        check("work dir removed", not (out_dir / ".~download_youtube_playlist~work").exists())
        check(
            "podcast batch not called",
            scrub_podcast.call_count == 0,
            str(scrub_podcast.call_count),
        )


def test_audio_routes_to_podcast_batch() -> None:
    print("\n--- test_audio_routes_to_podcast_batch ---")

    def fake_download(_url: str, output_dir: str, _media_type: str, **_kwargs) -> dict:
        results = []
        for index, url in enumerate(_URLS):
            path = Path(output_dir) / f"audio-{index}.m4a"
            path.write_text("downloaded")
            results.append({"url": url, "status": "downloaded", "output_path": str(path)})
        return {"downloaded": 2, "failed": 0, "results": results}

    def fake_scrub(_input_dir: str, output_dir: str, **_kwargs) -> dict:
        results = []
        for path in sorted(Path(_input_dir).iterdir()):
            output_path = Path(output_dir) / path.name
            output_path.write_text("scrubbed")
            results.append(
                {"input_path": str(path), "status": "processed", "output_path": str(output_path)}
            )
        return {"processed": 2, "skipped": 0, "failed": 0, "results": results}

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        with (
            patch.object(pipeline.download_youtube_media, "run", fake_download),
            patch.object(pipeline.batch_scrub_youtube_media, "run") as scrub_media,
            patch.object(pipeline.batch_scrub_youtube_podcast, "run", fake_scrub),
        ):
            result = pipeline.run(
                "https://playlist", str(out_dir), "audio", options={"verbose": False}
            )

        check("2 downloaded", result["downloaded"] == 2, str(result))
        check("2 processed", result["processed"] == 2, str(result))
        check("0 failed", result["failed"] == 0, str(result))
        check("scrubbed files exist", all((out_dir / f"audio-{i}.m4a").exists() for i in range(2)))
        check("work dir removed", not (out_dir / ".~download_youtube_playlist~work").exists())
        check("media batch not called", scrub_media.call_count == 0, str(scrub_media.call_count))


def test_music_downloads_audio_and_only_scrubs_names() -> None:
    print("\n--- test_music_downloads_audio_and_only_scrubs_names ---")
    captured = {}

    def fake_download(_url: str, output_dir: str, media_type: str, **_kwargs) -> dict:
        captured["download_media_type"] = media_type
        path = Path(output_dir) / "music-0.mka"
        path.write_text("downloaded")
        return {
            "downloaded": 1,
            "failed": 0,
            "results": [{"url": _URLS[0], "status": "downloaded", "output_path": str(path)}],
        }

    def fake_name_scrub(_input_dir: str, output_dir: str, **kwargs) -> dict:
        captured["scrub_options"] = kwargs["options"]
        source = next(Path(_input_dir).iterdir())
        destination = Path(output_dir) / "clean music.mka"
        destination.write_text("renamed")
        return {
            "processed": 1,
            "skipped": 0,
            "failed": 0,
            "results": [
                {
                    "input_path": str(source),
                    "status": "processed",
                    "output_path": str(destination),
                }
            ],
        }

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        with (
            patch.object(pipeline.download_youtube_media, "run", fake_download),
            patch.object(pipeline.batch_scrub_youtube_media, "run", fake_name_scrub),
            patch.object(pipeline.batch_scrub_youtube_podcast, "run") as scrub_podcast,
        ):
            result = pipeline.run(
                "https://playlist", str(out_dir), "music", options={"verbose": False}
            )

        check(
            "music downloads as audio",
            captured.get("download_media_type") == "audio",
            str(captured),
        )
        check(
            "name-only scrub enabled",
            captured["scrub_options"]["pipeline"].get("name_only") is True,
            str(captured),
        )
        check(
            "filename-only naming enabled",
            captured["scrub_options"]["pipeline"]["stages"]["suggest_name"]["filename_only"]
            is True,
            str(captured),
        )
        check("1 processed", result["processed"] == 1, str(result))
        check(
            "podcast batch not called",
            scrub_podcast.call_count == 0,
            str(scrub_podcast.call_count),
        )
        check("renamed file exists", (out_dir / "clean music.mka").exists())


def test_scrub_failure_rescues_raw_download() -> None:
    print("\n--- test_scrub_failure_rescues_raw_download ---")

    def fake_download(_url: str, output_dir: str, _media_type: str, **_kwargs) -> dict:
        path = Path(output_dir) / "raw.mkv"
        path.write_text("downloaded")
        return {
            "downloaded": 1,
            "failed": 0,
            "results": [{"url": _URLS[0], "status": "downloaded", "output_path": str(path)}],
        }

    def fake_scrub(input_dir: str, _output_dir: str, **_kwargs) -> dict:
        return {
            "processed": 0,
            "skipped": 0,
            "failed": 1,
            "results": [
                {
                    "input_path": str(Path(input_dir) / "raw.mkv"),
                    "status": "failed",
                    "output_path": None,
                }
            ],
        }

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        with (
            patch.object(pipeline.download_youtube_media, "run", fake_download),
            patch.object(pipeline.batch_scrub_youtube_media, "run", fake_scrub),
        ):
            pipeline.run("https://playlist", str(out_dir), "video", options={"verbose": False})

        check("raw file rescued", (out_dir / "raw.mkv").exists())
        check("work dir removed", not (out_dir / ".~download_youtube_playlist~work").exists())


def test_explicit_work_dir_used_and_removed() -> None:
    print("\n--- test_explicit_work_dir_used_and_removed ---")
    captured = {}

    def fake_download(_url: str, output_dir: str, _media_type: str, **_kwargs) -> dict:
        captured["download_dir"] = output_dir
        path = Path(output_dir) / "raw.mkv"
        path.write_text("downloaded")
        return {
            "downloaded": 1,
            "failed": 0,
            "results": [{"url": _URLS[0], "status": "downloaded", "output_path": str(path)}],
        }

    def fake_scrub(input_dir: str, output_dir: str, **_kwargs) -> dict:
        src = Path(input_dir) / "raw.mkv"
        dest = Path(output_dir) / "raw.mkv"
        dest.write_text("scrubbed")
        return {
            "processed": 1,
            "skipped": 0,
            "failed": 0,
            "results": [{"input_path": str(src), "status": "processed", "output_path": str(dest)}],
        }

    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        explicit_work_dir = Path(d) / "custom-download-dir"
        with (
            patch.object(pipeline.download_youtube_media, "run", fake_download),
            patch.object(pipeline.batch_scrub_youtube_media, "run", fake_scrub),
        ):
            pipeline.run(
                "https://playlist",
                str(out_dir),
                "video",
                work_dir=str(explicit_work_dir),
                options={"verbose": False},
            )

        check(
            "explicit work_dir used",
            captured.get("download_dir") == str(explicit_work_dir),
            str(captured),
        )
        check("explicit work_dir removed after run", not explicit_work_dir.exists())
        check(
            "default hidden work dir not created",
            not (out_dir / ".~download_youtube_playlist~work").exists(),
        )
        check("output landed in output_dir", (out_dir / "raw.mkv").exists())


def test_download_db_path_forwarded() -> None:
    print("\n--- test_download_db_path_forwarded ---")
    captured = {}

    def fake_download(*_args, **kwargs) -> dict:
        captured["db_path"] = kwargs.get("db_path")
        return {"downloaded": 0, "failed": 0, "results": []}

    scrub = Mock(return_value={"processed": 0, "skipped": 0, "failed": 0, "results": []})
    with tempfile.TemporaryDirectory() as d:
        out_dir = Path(d) / "out"
        with (
            patch.object(pipeline.download_youtube_media, "run", fake_download),
            patch.object(pipeline.batch_scrub_youtube_media, "run", scrub),
        ):
            pipeline.run(
                "https://playlist",
                str(out_dir),
                "video",
                db_path="/tmp/some_db.json",
                options={"verbose": False},
            )

        check("db path forwarded", captured.get("db_path") == "/tmp/some_db.json", str(captured))


if __name__ == "__main__":
    test_invalid_media_type()
    test_video_happy_path()
    test_audio_routes_to_podcast_batch()
    test_music_downloads_audio_and_only_scrubs_names()
    test_scrub_failure_rescues_raw_download()
    test_explicit_work_dir_used_and_removed()
    test_download_db_path_forwarded()

    print(f"\n{'=' * 40}")
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
