"""Stage: filter_podcast_audio — enhance spoken-word clarity for noisy listening.

Audio file goes in, audio file comes out with a speech-focused filter chain that
aims to make podcasts and rough voice recordings easier to follow in the car,
while walking, or in other noisy environments. The chain prioritizes consonant
clarity, consistent loudness, and explicit peak safety.

Filter chain:
  1. highpass (90 Hz)    — removes low-frequency rumble.
  2. lowpass (14 500 Hz) — trims brittle top-end noise while preserving speech air.
  3. EQ cut @ 200 Hz     — reduces low-mid mud and room buildup.
  4. EQ boost @ 3 500 Hz — strong speech-presence boost for intelligibility in noise.
  5. EQ cut @ 8 000 Hz   — tames harsh upper presence without losing air.
  6. deesser             — controls sharp "s" bursts so the presence boost does not
                           turn fatiguing.
  7. acompressor         — smooth gentle compression (ratio=2.5, long release=120 ms)
                           to keep words audible without pumping or sounding crushed.
  8. loudnorm            — single-pass EBU R128 normalization to target LUFS.
  9. aresample (soxr)    — high-quality resampler pass to clean up any filter artifacts.

Inputs:
    input_path  — path to source audio file
    output_path — path for filtered audio file (extension determines codec)

Options:
    highpass_hz          — low-frequency cutoff in Hz           (default: 90)
    lowpass_hz           — high-frequency cutoff in Hz          (default: 14500)
    eq_mud_hz            — centre of mud cut in Hz              (default: 200)
    eq_mud_gain          — gain in dB, negative = cut           (default: -2)
    eq_presence_hz       — centre of speech-presence boost, Hz  (default: 3500)
    eq_presence_gain     — gain in dB                           (default: 3.5)
    eq_air_hz            — centre of upper-presence cut in Hz   (default: 8000)
    eq_air_gain          — gain in dB, negative = cut           (default: -1.5)
    deesser_intensity    — ffmpeg deesser intensity             (default: 0.18)
    deesser_amount       — ffmpeg deesser max reduction         (default: 0.5)
    deesser_frequency    — ffmpeg deesser band focus (0..1)     (default: 0.56)
    compressor_threshold — threshold for compressor             (default: "-18dB")
    compressor_ratio     — compression ratio                    (default: 2.5)
    compressor_attack    — attack time in ms                    (default: 8)
    compressor_release   — release time in ms                   (default: 120)
    compressor_knee      — knee width in dB                     (default: 4)
    loudnorm_lufs        — target integrated loudness, LUFS     (default: -14)
    loudnorm_lra         — max loudness range, LU               (default: 7)
    loudnorm_tp          — true-peak ceiling, dBTP              (default: -2)
    output_format        — output container/codec: "same" (inherit source bitrate for
                           lossy outputs), "m4a", "mp3", "opus", "ogg", "flac", "wav"
                           When set, overrides codec selection regardless of the
                           output path extension. The output path extension and
                           this option should agree on the container.
                                                                 (default: "same")
    bitrate              — encoder bitrate for lossy codecs (ignored for lossless).
                           Omit when output_format="same" to inherit from input.
                           Required when output_format is set manually to a lossy
                           format.
                                                                 (default: None)
    verbose              — print progress                        (default: True)

Returns:
    dict with keys: output_path, codec

Example usage:
    from stages.filter_podcast_audio import run
    result = run("episode.opus", "episode_filtered.opus")
    result = run("episode.mp3", "episode_filtered.mp3", options={"loudnorm_lufs": -14})

    # CLI
    uv run stages/filter_podcast_audio.py --input episode.opus --output episode_filtered.opus
    uv run stages/filter_podcast_audio.py --input ep.mp3 --output ep_filtered.mp3 \\
        --options '{"bitrate": "256k"}'
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from pathlib import Path

from shared.ffprobe import get_audio_bitrate, get_streams
from shared.output import stage_header, stage_timer

log = logging.getLogger(__name__)

_STAGE = "filter_podcast_audio"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict = {
    "highpass_hz": 90,
    "lowpass_hz": 14500,
    "eq_mud_hz": 200,
    "eq_mud_gain": -2,
    "eq_presence_hz": 3500,
    "eq_presence_gain": 3.5,
    "eq_air_hz": 8000,
    "eq_air_gain": -1.5,
    "deesser_intensity": 0.18,
    "deesser_amount": 0.5,
    "deesser_frequency": 0.56,
    "compressor_threshold": "-18dB",
    "compressor_ratio": 2.5,
    "compressor_attack": 8,
    "compressor_release": 120,
    "compressor_knee": 4,
    "loudnorm_lufs": -14,
    "loudnorm_lra": 7,
    "loudnorm_tp": -2,
    "bitrate": None,
    "output_format": "same",  # "same" | "m4a" | "mp3" | "opus" | "ogg" | "flac" | "wav"
    "verbose": True,
}

# Codec selection by output container extension.
# Codecs listed here override the fallback (aac).
_CONTAINER_CODEC: dict[str, str] = {
    ".opus": "libopus",
    ".ogg": "libvorbis",
    ".mp3": "libmp3lame",
    ".flac": "flac",
    ".wav": "pcm_s16le",
}

# Codecs that don't accept a -b:a bitrate argument.
_NO_BITRATE_CODECS = {"flac", "pcm_s16le"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_speech_chain(opts: dict) -> str:
    hp = opts["highpass_hz"]
    lp = opts["lowpass_hz"]
    mud_f, mud_g = opts["eq_mud_hz"], opts["eq_mud_gain"]
    pre_f, pre_g = opts["eq_presence_hz"], opts["eq_presence_gain"]
    air_f, air_g = opts["eq_air_hz"], opts["eq_air_gain"]
    dess_i = opts["deesser_intensity"]
    dess_m = opts["deesser_amount"]
    dess_f = opts["deesser_frequency"]
    thr = opts["compressor_threshold"]
    rat = opts["compressor_ratio"]
    atk = opts["compressor_attack"]
    rel = opts["compressor_release"]
    knee = opts["compressor_knee"]

    filters = [
        f"highpass=f={hp}",
        f"lowpass=f={lp}",
        f"equalizer=f={mud_f}:t=q:w=1.0:g={mud_g}",
        f"equalizer=f={pre_f}:t=q:w=1.2:g={pre_g}",
        f"equalizer=f={air_f}:t=q:w=1.0:g={air_g}",
        f"deesser=i={dess_i}:m={dess_m}:f={dess_f}",
        (
            f"acompressor=threshold={thr}:ratio={rat}:attack={atk}:release={rel}:"
            f"knee={knee}:makeup=1"
        ),
    ]
    return ",".join(filters)


def _build_loudnorm_filter(opts: dict) -> str:
    lufs = opts["loudnorm_lufs"]
    lra = opts["loudnorm_lra"]
    tp = opts["loudnorm_tp"]
    return f"loudnorm=I={lufs}:LRA={lra}:TP={tp}:print_format=none"


def _run_ffmpeg(cmd: list[str], *, capture_output: bool = False) -> subprocess.CompletedProcess:
    log.debug("filter_podcast_audio command: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=capture_output,
        text=capture_output,
    )


def _probe_source_bitrate(src: Path) -> str:
    """Return source audio bitrate as 'Nk' string (e.g. '128k')."""
    bits = get_audio_bitrate(src)
    if bits is None:
        raise RuntimeError(f"Could not determine source bitrate for: {src}")
    kilobits = max(1, int(round(bits / 1000)))
    return f"{kilobits}k"


def _resolve_bitrate(
    src: Path, codec: str, output_format: str, requested_bitrate: str | None
) -> str | None:
    if codec in _NO_BITRATE_CODECS:
        return None
    if output_format == "same":
        return _probe_source_bitrate(src)
    if not requested_bitrate:
        raise ValueError("bitrate is required when output_format is set manually for lossy output")
    return requested_bitrate


def _probe_source_sample_rate(src: Path) -> int:
    """Return source audio sample rate, falling back to 48 kHz if unavailable."""
    streams = get_streams(src)
    return next(
        (
            int(stream["sample_rate"])
            for stream in streams
            if stream.get("codec_type") == "audio" and stream.get("sample_rate")
        ),
        48000,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(input_path: str, output_path: str, *, options: dict | None = None) -> dict:
    """Apply podcast intelligibility filter chain to an audio file.

    Raises:
        FileNotFoundError: if input does not exist.
        FileExistsError:   if output already exists.
        RuntimeError:      if ffmpeg fails.
    """
    opts = {**DEFAULTS, **(options or {})}
    src = Path(input_path)
    dst = Path(output_path)

    if not src.exists():
        raise FileNotFoundError(f"Input not found: {src}")
    if dst.exists():
        raise FileExistsError(f"Output already exists: {dst}")

    verbose = opts["verbose"]
    if verbose:
        stage_header(_STAGE, src, dst)

    speech_chain = _build_speech_chain(opts)
    output_format = opts["output_format"]
    if output_format and output_format != "same":
        lookup_ext = f".{output_format.lstrip('.')}"
    else:
        lookup_ext = dst.suffix.lower()
    codec = _CONTAINER_CODEC.get(lookup_ext, "aac")
    bitrate = _resolve_bitrate(src, codec, output_format, opts.get("bitrate"))

    tmp = dst.parent / (f".~{_STAGE}~" + dst.name)
    try:
        af_chain = f"{speech_chain},{_build_loudnorm_filter(opts)},aresample=resampler=soxr:precision=28"
        sample_rate = _probe_source_sample_rate(src)

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(src),
            "-vn",
            "-af",
            af_chain,
            "-c:a",
            codec,
        ]
        if bitrate is not None:
            cmd += ["-b:a", bitrate]
        cmd += [
            "-ar",
            str(sample_rate),
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-y",
            str(tmp),
        ]

        with stage_timer(_STAGE, "filtered"):
            result = _run_ffmpeg(cmd)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg failed (exit {result.returncode})")

        tmp.rename(dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    return {"output_path": str(dst), "codec": codec}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Apply podcast intelligibility filter chain to an audio file."
    )
    parser.add_argument("--input", required=True, help="Input audio file")
    parser.add_argument("--output", required=True, help="Output audio file")
    parser.add_argument("--options", default=None, help="JSON string of options")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    opts = json.loads(args.options) if args.options else None
    result = run(args.input, args.output, options=opts)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
