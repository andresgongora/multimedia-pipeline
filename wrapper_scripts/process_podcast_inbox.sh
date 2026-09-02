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
#   1. Runs pipelines.batch_scrub_youtube_podcast once over
#      <podcast-folder>/Inbox/, writing every eligible file's output into
#      the dated folder (filter, SponsorBlock cuts, metadata).
#   2. Trashes originals that were processed or already-skipped; keeps
#      originals that failed.
#   3. Cleans up any empty subdirectories left in Inbox/.
#
# The per-file batching itself lives in the pipeline
# (pipelines/batch_scrub_youtube_podcast.py) — this script only owns the
# personal policy the pipeline deliberately doesn't: trashing originals and
# the dated output-folder convention.
# ---------------------------------------------------------------------------

# SCRIPT_DIR = the folder where the symlink lives (the podcast folder).
# Resolving via $0 (not readlink) is intentional: we want the symlink's
# parent, not the script's source parent.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Inbox/ is where raw downloads are placed before processing.
INBOX="$SCRIPT_DIR/Inbox"

# Output goes into a dated subfolder created on first use each day.
OUTDIR="$SCRIPT_DIR/$(date +%Y.%m.%d)"

# Resolve the real location of this script (following the symlink) so we can
# cd into the project root and run uv from there, regardless of where the
# symlink lives.
REAL_SCRIPT="$(readlink -f "$0")"
PROJECT_DIR="$(cd "$(dirname "$REAL_SCRIPT")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -d "$INBOX" ]]; then
    echo "No Inbox found: $INBOX" >&2
    exit 0
fi

mkdir -p "$OUTDIR"

# ---------------------------------------------------------------------------
# Run the batch pipeline once over the whole Inbox/ (verbose off so stdout
# is clean JSON — the pipeline logs its own per-file progress to the
# terminal when run interactively without --options).
# ---------------------------------------------------------------------------

result_json="$(uv run -m pipelines.batch_scrub_youtube_podcast "$INBOX" "$OUTDIR" --force --options '{"verbose": false}')"

processed="$(jq '.processed' <<<"$result_json")"
skipped="$(jq '.skipped' <<<"$result_json")"
failed="$(jq '.failed' <<<"$result_json")"
echo "$processed processed, $skipped skipped, $failed failed"

# Trash originals that succeeded (processed or skipped); keep failures as-is.
jq -j '.results[] | select(.status != "failed") | .input_path + "\u0000"' <<<"$result_json" \
    | xargs -r -0 -I{} trash "{}" || true

# Remove any empty subdirectories left behind in Inbox/ after trashing files.
find "$INBOX" -mindepth 1 -type d -empty -delete 2>/dev/null || true

# ---------------------------------------------------------------------------
# Exit status
# ---------------------------------------------------------------------------

if [[ "$failed" -gt 0 ]]; then
    echo "$failed file(s) failed" >&2
    exit 1
fi
