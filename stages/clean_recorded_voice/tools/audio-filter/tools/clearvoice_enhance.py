#!/usr/bin/env python3
"""
clearvoice_enhance.py – Run ClearVoice MossFormer2_SE_48K speech enhancement on a WAV file.

Usage:
    python clearvoice_enhance.py <input.wav> <output.wav> [--model MODEL]

Requirements:
    pip install clearvoice

Models for speech_enhancement task:
    MossFormer2_SE_48K  (default – fullband 48 kHz, best for this project)
    FRCRN_SE_16K
    MossFormerGAN_SE_16K
"""

import argparse
import os
import sys
from pathlib import Path

# Redirect HuggingFace downloads to outputs/tmp/checkpoints/ so model weights
# never land in the project root or anywhere untracked outside outputs/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CHECKPOINT_DIR = _PROJECT_ROOT / "outputs" / "tmp" / "checkpoints"
_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(_CHECKPOINT_DIR))


##==================================================================================================
##  Requirements
##==================================================================================================


def check_clearvoice() -> None:
    """Validates that the clearvoice package is importable and prints the install hint if not."""
    try:
        import clearvoice  # noqa: F401
    except ImportError:
        print(
            "ERROR: 'clearvoice' package not found.\nInstall it with:  pip install clearvoice",
            file=sys.stderr,
        )
        sys.exit(1)


##==================================================================================================
##  Processing
##==================================================================================================


def enhance(input_path: Path, output_path: Path, model: str) -> None:
    """Loads the ClearVoice model and runs speech enhancement on the input file."""
    from clearvoice import ClearVoice  # import here so check_clearvoice() gives a clean error first

    print(f"[clearvoice] Loading model: {model}")
    cv = ClearVoice(task="speech_enhancement", model_names=[model])

    print(f"[clearvoice] Processing: {input_path}")
    output_wav = cv(input_path=str(input_path), online_write=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv.write(output_wav, output_path=str(output_path))
    print(f"[clearvoice] Output written: {output_path}")


##==================================================================================================
##  Main
##==================================================================================================


def parse_args() -> argparse.Namespace:
    """Parses and validates command-line arguments."""
    parser = argparse.ArgumentParser(
        description="ClearVoice speech enhancement wrapper (MossFormer2_SE_48K by default)."
    )
    parser.add_argument("input", type=Path, help="Input WAV file (48 kHz recommended).")
    parser.add_argument("output", type=Path, help="Output WAV file path.")
    parser.add_argument(
        "--model",
        default="MossFormer2_SE_48K",
        choices=["MossFormer2_SE_48K", "FRCRN_SE_16K", "MossFormerGAN_SE_16K"],
        help="ClearVoice model to use (default: MossFormer2_SE_48K).",
    )
    return parser.parse_args()


def main() -> None:
    """Orchestrates argument parsing, dependency checking, and enhancement."""
    args = parse_args()

    if not args.input.is_file():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    check_clearvoice()
    enhance(args.input, args.output, args.model)


if __name__ == "__main__":
    main()
