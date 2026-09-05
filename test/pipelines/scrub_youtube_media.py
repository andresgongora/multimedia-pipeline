"""Tests: scrub_youtube_media pipeline.

Usage:
    uv run test/pipelines/scrub_youtube_media.py

Tests:
  - Config loading and merging
  - Missing input raises FileNotFoundError
  - Full pipeline run on sample file (skips gracefully if no sample)
  - Force flag allows overwriting output
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pipelines.scrub_youtube_media as pipeline  # noqa: E402
from shared.config import load_config  # noqa: E402

_DEFAULT_CONFIG = ROOT / "pipelines" / "scrub_youtube_media.yaml"

SAMPLE_AUDIO = (
    ROOT / "test" / "sample" / "Wearing the Wrong Hat in the 1920’s Tales From the Bottle.m4a"
)
SAMPLE_VIDEO = (
    ROOT / "test" / "sample" / "Wearing the Wrong Hat in the 1920’s Tales From the Bottle.mp4"
)
SAMPLE_UNIDENTIFIABLE = ROOT / "test" / "sample" / "AUG.scrubbed.mp4"
OUTDIR = ROOT / "test" / "output"
OUTDIR.mkdir(exist_ok=True)

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


def cleanup(p: Path) -> None:
    p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Config tests (no network, no files)
# ---------------------------------------------------------------------------


def test_config_defaults() -> None:
    print("\n--- test_config_defaults ---")
    cfg = load_config(_DEFAULT_CONFIG)
    check("verbose defaults true", cfg.get("verbose") is True)
    check("name_only defaults false", cfg.get("name_only") is False)
    check("has stages section", isinstance(cfg.get("stages"), dict))
    check("has identify stage config", "identify" in cfg["stages"])
    check("has sponsorblock stage config", "sponsorblock" in cfg["stages"])
    check("has cut stage config", "cut" in cfg["stages"])


def test_config_merge() -> None:
    print("\n--- test_config_merge ---")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("verbose: false\nstages:\n  cut:\n    mode: fast\n")
        tmp_cfg = Path(f.name)
    try:
        cfg = load_config(_DEFAULT_CONFIG, tmp_cfg)
        check("override verbose", cfg.get("verbose") is False)
        check("override cut mode", cfg["stages"]["cut"]["mode"] == "fast")
        check("keeps identify defaults", "identify" in cfg["stages"])
    finally:
        tmp_cfg.unlink()


def test_missing_input_raises() -> None:
    print("\n--- test_missing_input_raises ---")
    try:
        pipeline.run("/definitely/nonexistent/file.m4a")
        check("raises FileNotFoundError", False, "no exception raised")
    except FileNotFoundError:
        check("raises FileNotFoundError", True)


# ---------------------------------------------------------------------------
# Integration test — full pipeline run
# ---------------------------------------------------------------------------


def test_pipeline_audio() -> None:
    """Run the full pipeline on the audio sample."""
    print("\n--- test_pipeline_audio ---")
    if not SAMPLE_AUDIO.exists():
        print("  SKIP  audio sample not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        result = pipeline.run(
            str(SAMPLE_AUDIO),
            output_dir=tmpdir,
            options={"verbose": True},
        )

        check("returns dict", isinstance(result, dict))
        check("has output_path", "output_path" in result)
        check("output file exists", Path(result["output_path"]).exists())
        check("output non-empty", Path(result["output_path"]).stat().st_size > 1000)
        check("has identified key", "identified" in result)
        check("has removed_segments key", "removed_segments" in result)
        check("has suggested_name", bool(result.get("suggested_name")))

        print(f"  INFO  identified:        {result['identified']}")
        print(f"  INFO  video_id:          {result.get('video_id')}")
        print(f"  INFO  sponsorblock:      {result.get('sponsorblock_found')}")
        print(f"  INFO  removed_segments:  {result.get('removed_segments')}")
        print(f"  INFO  suggested_name:    {result.get('suggested_name')!r}")
        print(f"  INFO  output:            {result.get('output_path')}")
        # Output is in tmpdir, will be cleaned up automatically


def test_pipeline_video() -> None:
    """Run the full pipeline on the video sample."""
    print("\n--- test_pipeline_video ---")
    if not SAMPLE_VIDEO.exists():
        print("  SKIP  video sample not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        result = pipeline.run(
            str(SAMPLE_VIDEO),
            output_dir=tmpdir,
            options={"verbose": True},
        )

        check("returns dict", isinstance(result, dict))
        check("output file exists", Path(result["output_path"]).exists())
        check("output non-empty", Path(result["output_path"]).stat().st_size > 1000)
        check("output is mp4", result["output_path"].endswith(".mp4"))

        print(f"  INFO  identified:       {result['identified']}")
        print(f"  INFO  suggested_name:   {result.get('suggested_name')!r}")


def test_pipeline_no_overwrite() -> None:
    """Must return {"skipped": True, ...} when output exists and force=False."""
    print("\n--- test_pipeline_no_overwrite ---")
    sample = SAMPLE_AUDIO if SAMPLE_AUDIO.exists() else SAMPLE_VIDEO
    if not sample.exists():
        print("  SKIP  no sample file available")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # First run
        result = pipeline.run(str(sample), output_dir=tmpdir, options={"verbose": False})
        out = Path(result["output_path"])
        check("first run produced output", out.exists())

        # Second run without force must skip, not raise
        result_skip = pipeline.run(
            str(sample), output_dir=tmpdir, force=False, options={"verbose": False}
        )
        check("second run returns skipped=True", result_skip.get("skipped") is True)
        check("skipped result keeps output_path", result_skip.get("output_path") == str(out))

        # With force=True it must succeed
        result2 = pipeline.run(
            str(sample), output_dir=tmpdir, force=True, options={"verbose": False}
        )
        check("force=True succeeds", Path(result2["output_path"]).exists())


def test_pipeline_no_sponsorblock_fallback() -> None:
    """Disabling search_fallback ensures the pipeline completes even without identification."""
    print("\n--- test_pipeline_no_sponsorblock_fallback ---")
    sample = SAMPLE_UNIDENTIFIABLE
    if not sample.exists():
        print(f"  SKIP  sample not found: {sample.name}")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        result = pipeline.run(
            str(sample),
            output_dir=tmpdir,
            options={
                "verbose": False,
                "stages": {"identify": {"search_fallback": False}},
            },
        )
        check("pipeline completed", isinstance(result, dict))
        check("not identified", result["identified"] is False)
        check("zero removed segments", result["removed_segments"] == 0)
        check("output exists", Path(result["output_path"]).exists())
        print(f"  INFO  suggested_name: {result.get('suggested_name')!r}")


def test_pipeline_unidentifiable_video() -> None:
    """Run pipeline on a video that cannot be identified on YouTube.

    AUG.scrubbed.mp4 has no YouTube ID in its filename or metadata.
    Expected behaviour (per pipeline design — stages degrade gracefully):
      - Pipeline completes without raising
      - identified = False
      - removed_segments = 0 (no SponsorBlock data)
      - Output file IS still written (scrub + rename still run)

    Output is kept in test/output/ for manual inspection.
    """
    print("\n--- test_pipeline_unidentifiable_video ---")
    if not SAMPLE_UNIDENTIFIABLE.exists():
        print(f"  SKIP  sample not found: {SAMPLE_UNIDENTIFIABLE.name}")
        return

    result = pipeline.run(
        str(SAMPLE_UNIDENTIFIABLE),
        output_dir=str(OUTDIR),
        force=True,
        options={"verbose": True},
    )

    check("returns dict", isinstance(result, dict))
    check("not identified", result.get("identified") is False)
    check("zero removed segments", result.get("removed_segments") == 0)
    check("output_path in result", "output_path" in result)
    output_exists = Path(result["output_path"]).exists()
    check("output file written", output_exists)

    print(f"  INFO  identified:      {result.get('identified')}")
    print(f"  INFO  removed_segments:{result.get('removed_segments')}")
    print(f"  INFO  suggested_name:  {result.get('suggested_name')!r}")
    print(f"  INFO  output:          {result.get('output_path')}")
    if not output_exists:
        print("  NOTE  output file was NOT written — pipeline did not produce a file")


def test_name_only_skips_media_processing() -> None:
    print("\n--- test_name_only_skips_media_processing ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        source = Path(tmpdir) / "Track (1080p) [dQw4w9WgXcQ].mka"
        source.write_text("audio")
        with (
            patch.object(
                pipeline.suggest_name,
                "run",
                return_value={"suggested_name": "Track"},
            ) as suggest,
            patch.object(pipeline.identify, "run") as identify,
            patch.object(pipeline.fetch_sponsorblock, "run") as sponsorblock,
            patch.object(pipeline.cut, "run") as cut,
            patch.object(pipeline.scrub_metadata, "run") as scrub_metadata,
        ):
            result = pipeline.run(
                str(source),
                output_dir=tmpdir,
                options={"verbose": False, "name_only": True},
            )

        check("name-only output exists", Path(result["output_path"]).exists())
        check("name-only output has clean name", Path(result["output_path"]).name == "Track.mka")
        check("source moved", not source.exists())
        check("name stage called", suggest.call_count == 1, str(suggest.call_count))
        check("identify skipped", identify.call_count == 0, str(identify.call_count))
        check("SponsorBlock skipped", sponsorblock.call_count == 0, str(sponsorblock.call_count))
        check("cut skipped", cut.call_count == 0, str(cut.call_count))
        check(
            "metadata scrub skipped",
            scrub_metadata.call_count == 0,
            str(scrub_metadata.call_count),
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_config_defaults()
    test_config_merge()
    test_missing_input_raises()
    test_pipeline_audio()
    test_pipeline_video()
    test_pipeline_no_overwrite()
    test_pipeline_no_sponsorblock_fallback()
    test_pipeline_unidentifiable_video()
    test_name_only_skips_media_processing()

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
