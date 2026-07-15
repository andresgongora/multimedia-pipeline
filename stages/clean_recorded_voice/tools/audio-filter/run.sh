#!/usr/bin/env bash
set -euo pipefail

##==================================================================================================
##  Main
##==================================================================================================

## Builds the Docker image if absent, then runs the audio pipeline against the current directory.
main() {
  if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <input_file> <output_file> [--dfn-atten-db=<0-100>]"
    echo ""
    echo "  Bare filenames are resolved under the current working directory."
    echo "  Builds the 'audio-filter' Docker image automatically if not present."
    echo ""
    echo "Examples:"
    echo "  ./run.sh sample.m4a outputs/sample_processed.m4a"
    echo "  ./run.sh sample.m4a outputs/sample_processed.m4a --dfn-atten-db=30"
    exit 1
  fi

  local script_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  local image_name="audio-filter"

  if ! docker image inspect "$image_name" >/dev/null 2>&1; then
    echo "Image '$image_name' not found — building..." >&2
    docker build -t "$image_name" "$script_dir"
  fi

  docker run --rm \
    -v "$(pwd)":/data \
    "$image_name" \
    "$1" "$2" "${@:3}"
}

main "$@"
