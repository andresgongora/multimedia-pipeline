#!/usr/bin/env bash
set -euo pipefail

##==================================================================================================
##  Requirements
##==================================================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/clearvoice_enhance.py"
VENV_PYTHON="${SCRIPT_DIR}/../.venv/bin/python3"

## Validates that a required command is available on PATH.
require_command() {
    local cmd="$1"
    if ! command -v "$cmd" &>/dev/null; then
        echo "ERROR: Required command not found: ${cmd}" >&2
        exit 1
    fi
}

## Validates that a required file exists.
require_file() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        echo "ERROR: File not found: ${path}" >&2
        exit 1
    fi
}

##==================================================================================================
##  Workflow helpers
##==================================================================================================

## Prints usage information and exits.
usage() {
    cat <<EOF
Usage: $(basename "$0") <input.wav> <output.wav> [MODEL]

Runs ClearVoice speech enhancement on a WAV file (48 kHz recommended).

Arguments:
  input.wav   Path to the input audio file.
  output.wav  Path for the enhanced output file.
  MODEL       ClearVoice model name (default: MossFormer2_SE_48K).
              Options: MossFormer2_SE_48K | FRCRN_SE_16K | MossFormerGAN_SE_16K

Requirements:
  - Python 3 with clearvoice installed: pip install clearvoice
  - Internet access on first run (models auto-downloaded from HuggingFace)

Example:
  $(basename "$0") input.wav outputs/enhanced.wav
  $(basename "$0") input.wav outputs/enhanced_16k.wav FRCRN_SE_16K
EOF
    exit 1
}

##==================================================================================================
##  Main
##==================================================================================================

## Orchestrates argument validation and delegates to the Python enhancement script.
main() {
    if [[ $# -lt 2 ]]; then
        usage
    fi

    local input_file="$1"
    local output_file="$2"
    local model="${3:-MossFormer2_SE_48K}"

    require_command fhs
    require_file "$PYTHON_SCRIPT"
    require_file "$VENV_PYTHON"
    require_file "$input_file"

    echo "[clearvoice] Input:  ${input_file}"
    echo "[clearvoice] Output: ${output_file}"
    echo "[clearvoice] Model:  ${model}"

    fhs -c "\"$VENV_PYTHON\" \"$PYTHON_SCRIPT\" \"$input_file\" \"$output_file\" --model \"$model\""

    echo "[clearvoice] Done."
}

main "$@"
