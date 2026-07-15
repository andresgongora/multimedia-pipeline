#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# Docker entrypoint for silence-remover
# Bare filenames resolve under /data (the mount point).
# ---------------------------------------------------------------------------

if [[ $# -lt 2 ]]; then
  echo "Usage: <input> <output> [threshold] [margin]"
  exit 1
fi

input_arg="$1"
output_arg="$2"
threshold="${3:-0.03}"
margin="${4:-0.25sec}"

[[ "$input_arg"  = /* ]] && input="$input_arg"  || input="/data/$input_arg"
[[ "$output_arg" = /* ]] && output="$output_arg" || output="/data/$output_arg"

if [[ ! -f "$input" ]]; then
  echo "Error: input not found: $input" >&2
  exit 1
fi

if [[ -f "$output" ]]; then
  echo "Error: output already exists: $output" >&2
  exit 1
fi

echo "==> Removing silences (threshold=${threshold}, margin=${margin})" >&2

# Probe rotation metadata from input (display matrix side data).
#
# Phone cameras (Android, iPhone) often record video with the sensor in a
# fixed physical orientation and store a rotation flag (display matrix) in
# the container metadata telling players to rotate during playback. For
# example, a phone held normally may produce 1920×1080 pixels stored
# landscape with rotation=-180 (or -90, 90, etc.) to display correctly.
#
# auto-editor re-encodes the video stream (it must, to cut at non-keyframe
# points) but does NOT apply the rotation transform to the pixels — yet it
# strips the display matrix from the output. The result is a video whose
# pixels are still in the raw sensor orientation but with no metadata telling
# players to rotate, so it appears upside-down or sideways.
#
# We probe the rotation here (inside the container, where the input is
# accessible) and print it to stderr as ROTATION=<degrees>. The host-side
# caller (stages/remove_silences/run.py _restore_rotation) parses this and
# re-applies the display matrix using the host ffmpeg, which is typically
# newer and supports -display_rotation.
rotation=$(ffprobe -v error -select_streams v:0 \
  -show_entries stream_side_data=rotation \
  -of default=noprint_wrappers=1:nokey=1 "$input" 2>/dev/null | head -1)

# Select audio codec based on output container format.
# MP4/M4A require a container-compatible codec (aac).
# WAV uses pcm_s16le by default. Let auto-editor decide for other formats.
output_ext="${output##*.}"
output_ext_lower="${output_ext,,}"

ae_audio_codec_args=()
if [[ "$output_ext_lower" == "mp4" || "$output_ext_lower" == "m4a" || "$output_ext_lower" == "mov" ]]; then
  ae_audio_codec_args=("-c:a" "aac")
fi

auto-editor "$input" \
  --edit "audio:threshold=${threshold}" \
  --margin "$margin" \
  "${ae_audio_codec_args[@]}" \
  --output "$output" \
  --no-open

# Emit rotation for the host-side caller to restore (see comment above).
if [[ -n "$rotation" && "$rotation" != "0" ]]; then
  echo "ROTATION=${rotation}" >&2
fi

echo "==> Done: $output" >&2
