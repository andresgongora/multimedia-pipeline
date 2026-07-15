#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# process_recorded_videos.sh
#
# Usage: process_recorded_videos.sh <video-folder> [--rotate 90|180|270]
#
# Layout expected in <video-folder>:
#   Raw/            ← drop raw video files here
#   Processed/      ← output lands here (created automatically)
#
# What it does (in order):
#   1. Runs extract_and_clean_voice on every video in Raw/ → Processed/
#   2. Runs remove_silences_and_extract_clean_voice on same files → Processed/
#      Optional rotate flag is forwarded to sanitize_video in that pipeline.
# ---------------------------------------------------------------------------

ROTATE=0

usage() {
    echo "Usage: $(basename "$0") <video-folder> [--rotate 90|180|270]" >&2
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

VIDEO_FOLDER_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rotate)
            if [[ $# -lt 2 ]]; then
                echo "Missing value for --rotate" >&2
                usage
                exit 1
            fi
            ROTATE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -* )
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
        *)
            if [[ -n "$VIDEO_FOLDER_ARG" ]]; then
                echo "Only one <video-folder> allowed" >&2
                usage
                exit 1
            fi
            VIDEO_FOLDER_ARG="$1"
            shift
            ;;
    esac
done

if [[ -z "$VIDEO_FOLDER_ARG" ]]; then
    usage
    exit 1
fi

case "$ROTATE" in
    0|90|180|270) ;;
    *)
        echo "Invalid --rotate value: $ROTATE (choose 0, 90, 180, 270)" >&2
        exit 1
        ;;
esac

VIDEO_FOLDER="$PWD/$VIDEO_FOLDER_ARG"
INPUT_FOLDER="$VIDEO_FOLDER/Raw"
OUTPUT_FOLDER="$VIDEO_FOLDER/Processed"

VIDEO_EXTS="mp4|mov|mkv|avi|mts|m2ts|webm"

REAL_SCRIPT="$(readlink -f "$0")"
PROJECT_DIR="$(cd "$(dirname "$REAL_SCRIPT")/.." && pwd)"
CALL_DIR="$(pwd)"
cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Collect video files
# ---------------------------------------------------------------------------

mapfile -t files < <(find "$INPUT_FOLDER" -maxdepth 1 -type f -regextype posix-extended -iregex ".*\\.($VIDEO_EXTS)$" 2>/dev/null)

if [[ ${#files[@]} -eq 0 ]]; then
    echo "No video files found in $INPUT_FOLDER"
    exit 0
fi

mkdir -p "$OUTPUT_FOLDER"

# ---------------------------------------------------------------------------
# Pass 1: extract and clean voice
# ---------------------------------------------------------------------------

echo "=== Pass 1: extract_and_clean_voice ==="
for f in "${files[@]}"; do
    nice uv run -m multimedia_pipeline extract-and-clean-voice -o "$OUTPUT_FOLDER" --force "$f"
done

# ---------------------------------------------------------------------------
# Pass 2: remove silences and extract clean voice
# ---------------------------------------------------------------------------

echo "=== Pass 2: remove_silences_and_extract_clean_voice ==="
for f in "${files[@]}"; do
    nice uv run -m multimedia_pipeline remove-silences-and-extract-clean-voice -o "$OUTPUT_FOLDER" --force --options "{\"stages\":{\"sanitize\":{\"rotate\":$ROTATE}}}" "$f"
done
