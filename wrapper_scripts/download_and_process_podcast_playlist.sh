#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# download_and_process_podcast_playlist.sh
#
# Meant to be symlinked into a podcast folder, e.g.:
#   ln -s ~/Software/multimedia-pipeline/wrapper_scripts/download_and_process_podcast_playlist.sh \
#         ~/Podcasts/download_and_process_podcast_playlist.sh
#
# One-call replacement for the download_podcast_playlist.sh +
# process_podcast_inbox.sh pair: downloads every new episode from a fixed
# playlist URL and scrubs it (SponsorBlock cuts, silence removal, metadata,
# M4A) in a single pipeline call (pipelines/download_youtube_playlist.py),
# instead of downloading into Inbox/ and separately processing it later.
#
# Layout expected in the symlink's parent folder:
#   <podcast-folder>/
#     .youtube_playlist         ← file containing the playlist URL (first line)
#     Inbox/                    ← disposable download work dir (wiped every run)
#     YYYY.MM.DD/                ← scrubbed output (created automatically per run)
#     .download_registry.json   ← dedup DB (created automatically)
#
# Inbox/ here is *not* a drop-and-process-later folder like in the
# process_podcast_inbox.sh workflow — it is an explicit work_dir passed to
# download_youtube_playlist, which owns it fully: created at the start of
# each run, removed at the end (see the pipeline's docstring). A file that
# downloads fine but fails scrubbing is rescued (moved raw) into the dated
# output folder instead of being lost with Inbox/.
# ---------------------------------------------------------------------------

# SCRIPT_DIR = the folder where the symlink lives (the podcast folder).
# Resolving via $0 (not readlink) is intentional: we want the symlink's
# parent, not the script's source parent.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

PLAYLIST_FILE="$SCRIPT_DIR/.youtube_playlist"
if [[ ! -f "$PLAYLIST_FILE" ]]; then
    echo "Missing playlist file: $PLAYLIST_FILE (create it with the playlist URL as its first line)" >&2
    exit 1
fi
PLAYLIST_URL="$(head -n 1 "$PLAYLIST_FILE" | tr -d '[:space:]')"
if [[ -z "$PLAYLIST_URL" ]]; then
    echo "Playlist file is empty: $PLAYLIST_FILE" >&2
    exit 1
fi

WORK_DIR="$SCRIPT_DIR/Inbox"
OUTDIR="$SCRIPT_DIR/$(date +%Y.%m.%d)"
DB_PATH="$SCRIPT_DIR/.download_registry.json"

mkdir -p "$OUTDIR"

# Resolve the real location of this script (following the symlink) so we can
# cd into the project root and run uv from there, regardless of where the
# symlink lives.
REAL_SCRIPT="$(readlink -f "$0")"
PROJECT_DIR="$(cd "$(dirname "$REAL_SCRIPT")/.." && pwd)"
cd "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# Download + scrub in one call (verbose off so stdout is clean JSON — the
# pipeline logs its own progress to the terminal when run interactively
# without --options).
# ---------------------------------------------------------------------------

result_json="$(uv run -m pipelines.download_youtube_playlist \
    "$PLAYLIST_URL" "$OUTDIR" audio \
    --work-dir "$WORK_DIR" --db "$DB_PATH" --force \
    --options '{"verbose": false}')"

downloaded="$(jq '.downloaded' <<<"$result_json")"
processed="$(jq '.processed' <<<"$result_json")"
skipped="$(jq '.skipped' <<<"$result_json")"
failed="$(jq '.failed' <<<"$result_json")"
echo "$downloaded downloaded, $processed processed, $skipped skipped, $failed failed"

# ---------------------------------------------------------------------------
# Exit status
# ---------------------------------------------------------------------------

if [[ "$failed" -gt 0 ]]; then
    echo "$failed failure(s) — check $OUTDIR for rescued raw (unscrubbed) files" >&2
    exit 1
fi
