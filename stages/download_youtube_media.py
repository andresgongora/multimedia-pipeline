"""Stage: download_youtube_media — download audio or video from a URL via yt-dlp.

Downloads either the full video (default up to 1080p, av1 codec preferred) or
audio-only (default: highest quality native stream, no forced transcode) from
any yt-dlp-supported URL, honoring language preference (default: original
audio track). Format selection falls back gracefully when the preferred
codec/language/resolution combination is unavailable.

The container of `output_path` is honored: if yt-dlp's selected stream
doesn't already match it, the file is remuxed (stream copy, no re-encode)
into the requested container.

Inputs:
    url         — source URL (e.g. a YouTube video URL)
    output_path — path for downloaded file (extension picks target container)

Options:
    media_type  — "video" (default) | "audio"
    resolution  — max video height in pixels (default: 1080; video only)
    video_codec — preferred video codec: "av1" (default), "vp9", "h264", "h265"
                  (falls back to any codec if unavailable)
    language    — preferred audio language track (default: "original";
                  falls back to any available language if not tagged/found)
    verbose     — print progress (default: True)

Returns:
    {
      "output_path": "...",
      "media_type":  "video",
      "format":      "<yt-dlp format selector used>",
      "remuxed":     False,
      "title":       "..." | None,
    }

Example usage:
    result = run("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video.mp4")

    result = run(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "audio.m4a",
        options={"media_type": "audio"},
    )

    # CLI
    uv run -m stages.download_youtube_media --input URL --output video.mp4
    uv run -m stages.download_youtube_media --input URL --output audio.opus \
        --options '{"media_type": "audio"}'
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from shared.output import stage_header, stage_timer

_STAGE = "download_youtube_media"

DEFAULTS: dict = {
    "media_type": "video",
    "resolution": 1080,
    "video_codec": "av1",
    "language": "original",
    "verbose": True,
}

_VCODEC_PREFIX: dict[str, str] = {
    "av1": "av01",
    "vp9": "vp09",
    "h264": "avc1",
    "h265": "hev1",
}


def _yt_dlp() -> list[str]:
    return [sys.executable, "-m", "yt_dlp"]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _build_video_format(resolution: int, codec: str, language: str | None) -> str:
    """Build a yt-dlp format selector, preferred codec/language first, looser fallbacks after."""
    codec_prefix = _VCODEC_PREFIX.get(codec, codec)
    lang_suffixes = [f"[language={language}]", ""] if language else [""]

    selectors: list[str] = []
    for suffix in lang_suffixes:
        selectors.append(
            f"bestvideo[height<={resolution}][vcodec^={codec_prefix}]{suffix}+bestaudio{suffix}"
        )
    for suffix in lang_suffixes:
        selectors.append(f"bestvideo[height<={resolution}]{suffix}+bestaudio{suffix}")
    selectors.append(f"best[height<={resolution}]")
    selectors.append("best")
    return "/".join(_dedupe(selectors))


def _build_audio_format(language: str | None) -> str:
    """Build a yt-dlp audio format selector: preferred language first, then any."""
    lang_suffixes = [f"[language={language}]", ""] if language else [""]
    selectors = [f"bestaudio{suffix}" for suffix in lang_suffixes]
    selectors.append("bestaudio")
    return "/".join(_dedupe(selectors))


def _remux_container(src: Path, dst: Path) -> None:
    """Copy streams from src into dst's container without re-encoding."""
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-c", "copy", str(dst)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg remux failed (exit {result.returncode}):\n{result.stderr.strip()}"
        )


def run(url: str, output_path: str, *, options: dict | None = None) -> dict:
    """Download audio or video from a URL.

    Raises:
        FileExistsError: if output already exists.
        ValueError:      if media_type is invalid.
        RuntimeError:    if yt-dlp or ffmpeg fails.
    """
    opts = {**DEFAULTS, **(options or {})}
    verbose = opts["verbose"]
    media_type = opts["media_type"]
    language = opts["language"]

    if media_type not in ("video", "audio"):
        raise ValueError(f"Unknown media_type '{media_type}'. Choose 'video' or 'audio'.")

    dst = Path(output_path)
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    if media_type == "video":
        fmt = _build_video_format(int(opts["resolution"]), opts["video_codec"], language)
    else:
        fmt = _build_audio_format(language)

    if verbose:
        stage_header(_STAGE, url, dst, {"media_type": media_type, "language": language})

    tmp_template = dst.parent / f".~{_STAGE}~{dst.stem}.%(ext)s"
    tmp_downloaded: Path | None = None

    try:
        with stage_timer(_STAGE, "downloaded"):
            cmd = [
                *_yt_dlp(),
                url,
                "-f",
                fmt,
                "-o",
                str(tmp_template),
                "--no-playlist",
                "--no-warnings",
                "--quiet",
                "--print",
                "%(title)s",
                "--print",
                "after_move:filepath",
            ]
            if media_type == "video":
                cmd += ["--merge-output-format", dst.suffix.lstrip(".")]

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"yt-dlp failed (exit {e.returncode}):\n{e.stderr.strip()}"
                ) from e
            except FileNotFoundError as e:
                raise RuntimeError("yt-dlp is not installed") from e

            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if not lines:
                raise RuntimeError("yt-dlp did not report a downloaded file path")
            title = lines[0] if len(lines) > 1 else None
            tmp_downloaded = Path(lines[-1])
            if not tmp_downloaded.exists():
                raise RuntimeError(f"yt-dlp reported missing file: {tmp_downloaded}")

        remuxed = False
        if tmp_downloaded.suffix.lower() == dst.suffix.lower():
            tmp_downloaded.rename(dst)
        else:
            _remux_container(tmp_downloaded, dst)
            remuxed = True
    finally:
        if tmp_downloaded is not None and tmp_downloaded.exists() and tmp_downloaded != dst:
            tmp_downloaded.unlink(missing_ok=True)

    return {
        "output_path": str(dst),
        "media_type": media_type,
        "format": fmt,
        "remuxed": remuxed,
        "title": title,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Download audio or video media from a URL.")
    parser.add_argument("--input", required=True, help="Source URL")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--options", type=json.loads, default="{}", help="JSON options")
    args = parser.parse_args()
    result = run(args.input, args.output, options=args.options)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
