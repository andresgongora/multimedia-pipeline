#!/usr/bin/env bash
set -euo pipefail

##==================================================================================================
##  Main
##==================================================================================================

## Validates arguments and delegates to filter.sh; resolves bare filenames relative to /data.
main() {
  if [[ $# -lt 2 ]]; then
    echo "Usage: docker run --rm -v /host/dir:/data <image> <input_file> <output_file> [options]"
    echo ""
    echo "Arguments:"
    echo "  input_file    Filename or absolute path to the input audio file (never modified)"
    echo "  output_file   Filename or absolute path for the processed output audio file"
    echo ""
    echo "  Bare filenames are resolved under /data (the mounted host directory)."
    echo ""
    echo "Options:"
    echo "  --dfn-atten-db=<0-100>      DeepFilterNet attenuation limit in dB (default: 20)"
    echo ""
    echo "Tip: Use ./run.sh from the project root to skip manual docker build/run."
    echo ""
    echo "Examples:"
    echo "  docker run --rm -v \"\$(pwd)\":/data <image> input.m4a output.m4a"
    echo "  docker run --rm -v \"\$(pwd)\":/data <image> input.m4a output.m4a --dfn-atten-db=30"
    exit 1
  fi

  local input_arg="$1"
  local output_arg="$2"

  # Resolve bare filenames to /data so the host-mounted volume is always the target.
  local input_file output_file
  [[ "$input_arg" = /* ]] && input_file="$input_arg"   || input_file="/data/$input_arg"
  [[ "$output_arg" = /* ]] && output_file="$output_arg" || output_file="/data/$output_arg"

  [[ -f "$input_file" ]] || {
    echo "Error: input file not found: $input_file"
    exit 1
  }

  exec /app/filter.sh "$input_file" "$output_file" "${@:3}"
}

main "$@"
