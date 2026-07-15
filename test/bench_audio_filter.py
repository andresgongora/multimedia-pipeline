"""Benchmark: audio filter configurations for filter_podcast_audio stage.

Runs multiple ffmpeg filter chains against a sample podcast file, times each,
measures output loudness/peak, and writes named output files for A/B listening.

Round 4 — base is I (A mud + 3500 Hz +3.5 dB + deesser). Vary compressor only.
  I_ref       — reference: ratio=3, attack=5,  release=80,  knee=3
  K_soft      — gentler:   ratio=2, attack=10, release=100, knee=4  (more natural dynamics)
  L_hard      — tighter:   ratio=4, attack=3,  release=60,  knee=2  (more levelled)
  M_punch     — punchy:    ratio=3, attack=15, release=60,  knee=3  (slower attack = transients)
  N_smooth    — smooth:    ratio=2.5, attack=8, release=120, knee=4 (between K and I)

Usage:
    uv run test/bench_audio_filter.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SAMPLE = ROOT / "test/sample/Wearing the Wrong Hat in the 1920\u2019s Tales From the Bottle.m4a"
OUTPUT_DIR = ROOT / "test/output"
OUTPUT_CODEC = "libmp3lame"
OUTPUT_EXT = ".mp3"
OUTPUT_BITRATE = "128k"  # match source

# Target for loudness check
TARGET_LUFS = -14.0
LUFS_TOLERANCE = 2.0


# ---------------------------------------------------------------------------
# Filter chain builders
# ---------------------------------------------------------------------------


def _chain_A_legacy() -> str:
    """Exact legacy bash filter chain."""
    return ",".join([
        "highpass=f=90",
        "lowpass=f=14500",
        "equalizer=f=200:t=q:w=1.0:g=-2",
        "equalizer=f=3500:t=q:w=1.2:g=3",
        "equalizer=f=8000:t=q:w=1.0:g=-1.5",
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=80:knee=3:makeup=1",
        "loudnorm=I=-14:LRA=7:TP=-2:print_format=none",
        "aresample=resampler=soxr:precision=28",
    ])


def _chain_I_ref() -> str:
    """Reference I: A mud + 3500 Hz +3.5 dB + deesser, ratio=3, attack=5, release=80."""
    return ",".join([
        "highpass=f=90",
        "lowpass=f=14500",
        "equalizer=f=200:t=q:w=1.0:g=-2",
        "equalizer=f=3500:t=q:w=1.2:g=3.5",
        "equalizer=f=8000:t=q:w=1.0:g=-1.5",
        "deesser=i=0.18:m=0.5:f=0.56",
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=80:knee=3:makeup=1",
        "loudnorm=I=-14:LRA=7:TP=-2:print_format=none",
        "aresample=resampler=soxr:precision=28",
    ])


def _chain_K_soft() -> str:
    """I + softer comp: ratio=2, attack=10, release=100, knee=4 — more natural dynamics."""
    return ",".join([
        "highpass=f=90",
        "lowpass=f=14500",
        "equalizer=f=200:t=q:w=1.0:g=-2",
        "equalizer=f=3500:t=q:w=1.2:g=3.5",
        "equalizer=f=8000:t=q:w=1.0:g=-1.5",
        "deesser=i=0.18:m=0.5:f=0.56",
        "acompressor=threshold=-18dB:ratio=2:attack=10:release=100:knee=4:makeup=1",
        "loudnorm=I=-14:LRA=7:TP=-2:print_format=none",
        "aresample=resampler=soxr:precision=28",
    ])


def _chain_L_hard() -> str:
    """I + harder comp: ratio=4, attack=3, release=60, knee=2 — more levelled."""
    return ",".join([
        "highpass=f=90",
        "lowpass=f=14500",
        "equalizer=f=200:t=q:w=1.0:g=-2",
        "equalizer=f=3500:t=q:w=1.2:g=3.5",
        "equalizer=f=8000:t=q:w=1.0:g=-1.5",
        "deesser=i=0.18:m=0.5:f=0.56",
        "acompressor=threshold=-18dB:ratio=4:attack=3:release=60:knee=2:makeup=1",
        "loudnorm=I=-14:LRA=7:TP=-2:print_format=none",
        "aresample=resampler=soxr:precision=28",
    ])


def _chain_M_punch() -> str:
    """I + punchy comp: ratio=3, attack=15, release=60, knee=3 — slower attack preserves transients."""
    return ",".join([
        "highpass=f=90",
        "lowpass=f=14500",
        "equalizer=f=200:t=q:w=1.0:g=-2",
        "equalizer=f=3500:t=q:w=1.2:g=3.5",
        "equalizer=f=8000:t=q:w=1.0:g=-1.5",
        "deesser=i=0.18:m=0.5:f=0.56",
        "acompressor=threshold=-18dB:ratio=3:attack=15:release=60:knee=3:makeup=1",
        "loudnorm=I=-14:LRA=7:TP=-2:print_format=none",
        "aresample=resampler=soxr:precision=28",
    ])


def _chain_N_smooth() -> str:
    """I + smooth comp: ratio=2.5, attack=8, release=120, knee=4 — between K and I."""
    return ",".join([
        "highpass=f=90",
        "lowpass=f=14500",
        "equalizer=f=200:t=q:w=1.0:g=-2",
        "equalizer=f=3500:t=q:w=1.2:g=3.5",
        "equalizer=f=8000:t=q:w=1.0:g=-1.5",
        "deesser=i=0.18:m=0.5:f=0.56",
        "acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120:knee=4:makeup=1",
        "loudnorm=I=-14:LRA=7:TP=-2:print_format=none",
        "aresample=resampler=soxr:precision=28",
    ])


CONFIGS: list[tuple[str, str, str]] = [
    ("I_ref",   "Reference I: ratio=3 attack=5  release=80  knee=3",  _chain_I_ref()),
    ("K_soft",  "Soft comp:   ratio=2 attack=10 release=100 knee=4",  _chain_K_soft()),
    ("L_hard",  "Hard comp:   ratio=4 attack=3  release=60  knee=2",  _chain_L_hard()),
    ("M_punch", "Punchy comp: ratio=3 attack=15 release=60  knee=3",  _chain_M_punch()),
    ("N_smooth","Smooth comp: ratio=2.5 attack=8 release=120 knee=4", _chain_N_smooth()),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def measure_loudness(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-y",
            "-i", str(path),
            "-af", "loudnorm=I=-14:TP=-1:LRA=7:print_format=json",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    match = re.search(r'\{[^{}]*"input_i"[^{}]*\}', combined, re.DOTALL)
    if not match:
        raise RuntimeError(f"Could not parse loudnorm JSON:\n{combined[-1500:]}")
    data = json.loads(match.group())
    return {
        "lufs": float(data["input_i"]),
        "tp": float(data["input_tp"]),
    }


def run_config(name: str, description: str, af_chain: str, src: Path) -> dict:
    dst = OUTPUT_DIR / f"bench_{name}{OUTPUT_EXT}"
    if dst.exists():
        dst.unlink()

    cmd = [
        "ffmpeg", "-hide_banner",
        "-i", str(src),
        "-vn",
        "-af", af_chain,
        "-c:a", OUTPUT_CODEC,
        "-b:a", OUTPUT_BITRATE,
        "-y",
        str(dst),
    ]

    print(f"\n{'='*60}")
    print(f"  {name}: {description}")
    print(f"  Filter: {af_chain[:120]}{'...' if len(af_chain) > 120 else ''}")
    t0 = time.perf_counter()
    result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    elapsed = time.perf_counter() - t0

    if result.returncode != 0:
        print(f"  ERROR (exit {result.returncode}):")
        print(result.stderr[-800:])
        return {"name": name, "description": description, "elapsed": elapsed, "error": True,
                "output": str(dst)}

    loudness = measure_loudness(dst)
    size_kb = dst.stat().st_size // 1024

    print(f"  Time : {elapsed:.1f}s")
    print(f"  LUFS : {loudness['lufs']:.2f}  (target {TARGET_LUFS})")
    print(f"  TP   : {loudness['tp']:.2f} dBTP")
    print(f"  Size : {size_kb} KB")
    print(f"  Out  : {dst.name}")

    return {
        "name": name,
        "description": description,
        "elapsed": elapsed,
        "lufs": loudness["lufs"],
        "tp": loudness["tp"],
        "size_kb": size_kb,
        "output": str(dst),
        "error": False,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not SAMPLE.exists():
        print(f"SKIP — sample not found: {SAMPLE}")
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Benchmark: audio filter configurations")
    print(f"Input : {SAMPLE.name}")
    print(f"Output: {OUTPUT_DIR}")

    results = []
    for name, description, chain in CONFIGS:
        r = run_config(name, description, chain, SAMPLE)
        results.append(r)

    # Summary table
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    header = f"{'Name':<18} {'Time(s)':>7}  {'LUFS':>7}  {'TP':>6}  {'KB':>6}  Description"
    print(header)
    print("-" * len(header))
    fastest = min((r["elapsed"] for r in results if not r.get("error")), default=None)
    for r in results:
        if r.get("error"):
            print(f"{r['name']:<18} {'ERROR':>7}  {'--':>7}  {'--':>6}  {'--':>6}  {r['description']}")
        else:
            speed_marker = " ★" if r["elapsed"] == fastest else ""
            print(
                f"{r['name']:<18} {r['elapsed']:>7.1f}  {r['lufs']:>7.2f}  {r['tp']:>6.2f}"
                f"  {r['size_kb']:>6}  {r['description']}{speed_marker}"
            )
    print(f"\nListen to test/output/bench_*.mp3 to score quality.")
    print(f"★ = fastest")


if __name__ == "__main__":
    main()
