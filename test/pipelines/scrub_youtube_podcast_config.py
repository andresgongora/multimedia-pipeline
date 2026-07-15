"""Regression test: blank convert_to_wav config remains valid.

Usage:
    uv run test/pipelines/scrub_youtube_podcast_config.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipelines import scrub_youtube_podcast as pipeline  # noqa: E402


def write_output(_input_path: str, output_path: str, *_args: object, **_kwargs: object) -> dict:
    Path(output_path).touch()
    return {"output_path": output_path}


with tempfile.TemporaryDirectory() as temp_dir:
    source = Path(temp_dir) / "episode.m4a"
    source.touch()
    output_dir = Path(temp_dir) / "output"
    conversion_options: list[dict | None] = [None]

    def convert(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
        conversion_options[0] = options
        return write_output(input_path, output_path)

    with (
        patch.object(pipeline.identify, "run", return_value={"identified": False}),
        patch.object(pipeline.convert_to_wav, "run", side_effect=convert),
        patch.object(pipeline.cut, "run", side_effect=write_output),
        patch.object(pipeline.remove_silences, "run", side_effect=write_output),
        patch.object(pipeline.filter_podcast_audio, "run", side_effect=write_output),
        patch.object(pipeline.scrub_metadata, "run", side_effect=write_output),
        patch.object(pipeline.add_metadata, "run", side_effect=write_output),
        patch.object(pipeline.suggest_name, "run", return_value={"suggested_name": "clean"}),
        patch.object(pipeline, "_get_local_duration", return_value=None),
    ):
        result = pipeline.run(str(source), output_dir=str(output_dir), options={"verbose": False})

    assert Path(result["output_path"]).exists(), result
    assert conversion_options[0] == {"verbose": False}, conversion_options[0]

print("PASS")
