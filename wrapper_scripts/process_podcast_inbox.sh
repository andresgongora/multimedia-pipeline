#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# process_podcast_inbox.sh
#
# Meant to be symlinked into a podcast folder, e.g.:
#   ln -s ~/Software/multimedia-pipeline/wrapper_scripts/process_podcast_inbox.sh \
#         ~/Podcasts/process_podcast_inbox.sh
#
# Layout expected in the symlink's parent folder:
#   <podcast-folder>/
#     Inbox/           ← drop raw downloads here
#     YYYY.MM.DD/      ← processed output (created automatically per run)
#
# What it does:
#   1. Finds all audio files in <podcast-folder>/inbox/
#   2. Runs scrub-youtube-podcast on each (filter, SponsorBlock cuts, metadata)
#   3. Moves processed output to a dated subfolder
#   4. Trashes the original on success; keeps it on failure
#   5. Cleans up any empty subdirectories left in inbox/
# ---------------------------------------------------------------------------

# SCRIPT_DIR = the folder where the symlink lives (the podcast folder).
# Resolving via $0 (not readlink) is intentional: we want the symlink's
# parent, not the script's source parent.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Inbox/ is where raw downloads are placed before processing.
INBOX="$SCRIPT_DIR/Inbox"

# Output goes into a dated subfolder created on first use each day.
OUTDIR="$SCRIPT_DIR/$(date +%Y.%m.%d)"

# Supported audio extensions (case-insensitive match via find's -iregex).
AUDIO_EXTS="m4a|mp3|opus|flac|wav|ogg|aac"

# Resolve the real location of this script (following the symlink) so we can
# cd into the project root and run uv from there, regardless of where the
# symlink lives.
REAL_SCRIPT="$(readlink -f "$0")"
PROJECT_DIR="$(cd "$(dirname "$REAL_SCRIPT")/.." && pwd)"
cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Collect audio files
# ---------------------------------------------------------------------------

mapfile -t files < <(find "$INBOX" -type f -regextype posix-extended -iregex ".*\\.($AUDIO_EXTS)$" 2>/dev/null)

if [[ ${#files[@]} -eq 0 ]]; then
    echo "No audio files found in Inbox/"
    exit 0
fi

mkdir -p "$OUTDIR"

# ---------------------------------------------------------------------------
# Process each file
# ---------------------------------------------------------------------------

errors=0
for f in "${files[@]}"; do
    echo "▶ $f"
    if uv run -m multimedia_pipeline scrub-youtube-podcast -o "$OUTDIR" --force "$f"; then
        # Original safely processed — move to trash rather than hard-delete.
        trash "$f"
    else
        echo "✗ Failed: $f (kept original)" >&2
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
