#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# download_videos.sh
#
# Meant to be symlinked into a video folder, e.g.:
#   ln -s ~/Software/multimedia-pipeline/wrapper_scripts/download_videos.sh \
#         ~/Videos/YouTube/download_videos.sh
#
# Downloads every new video from a fixed playlist URL into Inbox/, so
# process_youtube_inbox.sh can pick them up on the next manual run (this
# script does not chain into scrub-youtube-media itself).
#
# Layout expected in the symlink's parent folder:
#   <video-folder>/
#     Inbox/                    ← downloaded video lands here
#     .download_registry.json   ← dedup DB (created automatically)
#
# Edit PLAYLIST_URL below before use.
# ---------------------------------------------------------------------------

# TODO: set the real playlist URL before running this script.
PLAYLIST_URL="https://www.youtube.com/playlist?list=TODO_PLACEHOLDER"

# SCRIPT_DIR = the folder where the symlink lives (the video folder).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

OUTDIR="$SCRIPT_DIR/Inbox"
DB_PATH="$SCRIPT_DIR/.download_registry.json"

mkdir -p "$OUTDIR"

# Resolve the real location of this script (following the symlink) so we can
# cd into the project root and run uv from there, regardless of where the
# symlink lives.
REAL_SCRIPT="$(readlink -f "$0")"
PROJECT_DIR="$(cd "$(dirname "$REAL_SCRIPT")/.." && pwd)"
cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

uv run -m multimedia_pipeline download-youtube-media \
    "$PLAYLIST_URL" "$OUTDIR" --type video --db "$DB_PATH"
