#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# silence-remover/run.sh — Host wrapper for silence-remover Docker tool
#
# Builds the Docker image if absent, then runs auto-editor in a container.
# Bare filenames resolve under the caller's CWD (mounted as /data).
#
# Usage:  ./run.sh <input> <output> [threshold] [margin]
# ---------------------------------------------------------------------------

main() {
  if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <input> <output> [threshold] [margin]"
    echo ""
    echo "  threshold  Linear amplitude 0-1 (default: 0.03 ≈ -30 dB)"
    echo "  margin     Padding per cut side (default: 0.25sec)"
    exit 1
  fi

  local script_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  local image_name="silence-remover"

  if ! docker image inspect "$image_name" >/dev/null 2>&1; then
    echo "Image '$image_name' not found — building..." >&2
    docker build -t "$image_name" "$script_dir"
  fi

  docker run --rm \
    -v "$(pwd)":/data \
    "$image_name" \
    "$@"
}

main "$@"
