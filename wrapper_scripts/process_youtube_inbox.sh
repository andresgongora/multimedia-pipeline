#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# process_youtube_inbox.sh
#
# Meant to be symlinked into a video folder, e.g.:
#   ln -s ~/Software/multimedia-pipeline/wrapper_scripts/process_youtube_inbox.sh \
#         ~/Videos/YouTube/process_youtube_inbox.sh
#
# Layout expected in the symlink's parent folder:
#   <video-folder>/
#     Inbox/           ← drop raw downloads here
#     YYYY.MM.DD/      ← processed output (created automatically per run)
#
# What it does:
#   1. Finds all video files in <video-folder>/Inbox/
#   2. Runs scrub-youtube-media on each:
#        - Identifies the video on YouTube
#        - Fetches SponsorBlock segments (sponsors, intros, outros, etc.)
#        - Cuts them out in "fast" mode (stream-copy, no re-encode)
#        - Scrubs privacy-sensitive metadata and embeds clean metadata
#        - Suggests a clean filename and writes output to the dated folder
#   3. Trashes the original on success; keeps it on failure
#   4. Cleans up any empty subdirectories left in Inbox/
# ---------------------------------------------------------------------------

# SCRIPT_DIR = the folder where the symlink lives (the video folder).
# Resolving via $0 (not readlink) is intentional: we want the symlink's
# parent, not the script's source parent.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Inbox/ is where raw downloads are placed before processing.
INBOX="$SCRIPT_DIR/Inbox"

# Output goes into a dated subfolder created on first use each day.
OUTDIR="$SCRIPT_DIR/$(date +%Y.%m.%d)"

# Supported video extensions (case-insensitive match via find's -iregex).
VIDEO_EXTS="mp4|mkv|webm|mov|m4v|avi|ts|m2ts|mts"

# Resolve the real location of this script (following the symlink) so we can
# cd into the project root and run uv from there, regardless of where the
# symlink lives.
REAL_SCRIPT="$(readlink -f "$0")"
PROJECT_DIR="$(cd "$(dirname "$REAL_SCRIPT")/.." && pwd)"
cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Collect video files
# ---------------------------------------------------------------------------

mapfile -t files < <(find "$INBOX" -type f -regextype posix-extended -iregex ".*\\.($VIDEO_EXTS)$" 2>/dev/null)

if [[ ${#files[@]} -eq 0 ]]; then
    echo "No video files found in Inbox/"
    exit 0
fi

mkdir -p "$OUTDIR"

# ---------------------------------------------------------------------------
# Process each file
#
# Cut mode is "fast" by default (pipelines/scrub_youtube_media.yaml):
#   stages.cut.mode: fast
# This means SponsorBlock segments are removed via stream-copy (no re-encode).
# ---------------------------------------------------------------------------

errors=0
for f in "${files[@]}"; do
    echo "▶ $f"
    if uv run -m multimedia_pipeline scrub-youtube-media -o "$OUTDIR" --force "$f"; then
        # Original safely processed — move to trash rather than hard-delete.
        trash "$f"
    else
        # Pipeline could not process the file (e.g. unsupported codec, no
        # YouTube match). Move it as-is to the output folder so it ends up
        # alongside the successfully processed files rather than blocking Inbox.
        echo "✗ Failed: $f — moving original to $OUTDIR/" >&2
        mv "$f" "$OUTDIR/"
        ((errors++)) || true
    fi
done

# Remove any empty subdirectories left behind in Inbox/ after trashing files.
find "$INBOX" -mindepth 1 -type d -empty -delete 2>/dev/null || true

# ---------------------------------------------------------------------------
# Exit status
# ---------------------------------------------------------------------------

if [[ $errors -gt 0 ]]; then
    echo "$errors file(s) failed" >&2
    exit 1
fi
