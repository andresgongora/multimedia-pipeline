#!/usr/bin/env python3
"""
Offline WPE dereverberation script.

Converts a mono or multi-channel audio file (any format ffmpeg can decode)
to a dereverberated WAV using the nara_wpe Numpy implementation.

Usage:
    uv run tools/dereverb_wpe.py <input_audio> [output_wav]

If output_wav is omitted, the result is written next to the input file with
the suffix _dereverb.wav.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from nara_wpe.utils import istft, stft
from nara_wpe.wpe import wpe

##==================================================================================================
##  Configuration
##==================================================================================================

STFT_OPTIONS = dict(size=512, shift=128)

# WPE parameters (tuned for single-channel / near-single-channel speech)
DELAY = 3
TAPS = 10
ITERATIONS = 5
ALPHA = 0.9999

##==================================================================================================
##  Helpers
##==================================================================================================


## Decodes non-WAV audio to temporary PCM WAV via ffmpeg, preserving sample rate.
def decode_to_wav(input_path: Path, tmp_dir: Path) -> Path:
    # If already a WAV, use it directly — no re-encoding needed.
    if input_path.suffix.lower() == ".wav":
        return input_path

    wav_path = tmp_dir / "input_decoded.wav"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",  # mono – WPE works best with a single channel for this script
        "-sample_fmt",
        "s16",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"ffmpeg decoding failed for {input_path}")
    return wav_path


## Loads a WAV file and returns (signal, sample_rate) with shape (channels, samples).
def load_audio(wav_path: Path):
    data, sr = sf.read(str(wav_path), always_2d=True)
    # soundfile gives (samples, channels); WPE expects (channels, samples)
    return data.T, sr


## Applies offline WPE dereverberation and returns the processed signal (channels, samples).
def apply_wpe(y: np.ndarray) -> np.ndarray:
    print(f"  Input shape : {y.shape}  (channels, samples)")

    Y = stft(y, **STFT_OPTIONS).transpose(2, 0, 1)  # (freq, channels, frames)

    Z = wpe(
        Y,
        taps=TAPS,
        delay=DELAY,
        iterations=ITERATIONS,
        statistics_mode="full",
    ).transpose(1, 2, 0)  # (channels, frames, freq)

    z = istft(Z, size=STFT_OPTIONS["size"], shift=STFT_OPTIONS["shift"])
    print(f"  Output shape: {z.shape}  (channels, samples)")
    return z


## Saves a (channels, samples) array as a WAV file.
def save_wav(signal: np.ndarray, sample_rate: int, output_path: Path) -> None:
    # soundfile expects (samples, channels)
    sf.write(str(output_path), signal.T, sample_rate, subtype="PCM_16")


##==================================================================================================
##  Main
##==================================================================================================


## Orchestrates decoding, WPE dereverberation, and saving the result.
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1]).resolve()
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2]).resolve()
    else:
        output_path = input_path.with_name(input_path.stem + "_dereverb.wav")

    print(f"Input  : {input_path}")
    print(f"Output : {output_path}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        print("\n[1/3] Decoding audio …")
        wav_path = decode_to_wav(input_path, tmp_path)

        print("[2/3] Loading WAV …")
        y, sr = load_audio(wav_path)
        print(f"  Sample rate : {sr} Hz  (preserved, no resampling)")

        print("[3/3] Applying WPE dereverberation …")
        z = apply_wpe(y)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_wav(z, sr, output_path)
    print(f"\nDone. Dereverberated file saved to:\n  {output_path}")


main()
