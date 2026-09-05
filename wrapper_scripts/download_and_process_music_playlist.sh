#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

##==================================================================================================
##	DEPENDENCY CHECKS
##==================================================================================================

requireCommand() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$1" >&2
        exit 1
    fi
}

requireCommand date
requireCommand jq
requireCommand mkdir
requireCommand readlink
requireCommand uv

##==================================================================================================
##	GLOBALS
##==================================================================================================

case "$0" in
    */*) declare -r SCRIPT_PARENT="${0%/*}" ;;
    *) declare -r SCRIPT_PARENT="." ;;
esac

SCRIPT_DIR="$(cd "$SCRIPT_PARENT" && pwd)"
declare -r SCRIPT_DIR
PLAYLIST_FILE="$SCRIPT_DIR/.youtube_playlist"
declare -r PLAYLIST_FILE
WORK_DIR="$SCRIPT_DIR/Inbox"
declare -r WORK_DIR
OUTPUT_DIR="$SCRIPT_DIR/$(date +%G.W%V)"
declare -r OUTPUT_DIR
DB_PATH="$SCRIPT_DIR/.download_registry.json"
declare -r DB_PATH

##==================================================================================================
##	UTILITIES
##==================================================================================================

die() {
    printf '%s\n' "$1" >&2
    exit 1
}

##==================================================================================================
##	CORE FUNCTIONS
##==================================================================================================

readPlaylistUrl() {
    local playlist_file="$1"
    local playlist_url

    [[ -f "$playlist_file" ]] || die "Missing playlist file: $playlist_file"
    IFS= read -r playlist_url < "$playlist_file" || true
    playlist_url="${playlist_url//[[:space:]]/}"
    [[ -n "$playlist_url" ]] || die "Playlist file is empty: $playlist_file"
    printf '%s' "$playlist_url"
}

processPlaylist() {
    local playlist_url="$1"
    local output_dir="$2"
    local work_dir="$3"
    local db_path="$4"
    local result_json
    local downloaded
    local processed
    local skipped
    local failed

    mkdir -p "$output_dir"
    result_json="$(uv run -m pipelines.download_youtube_playlist \
        "$playlist_url" "$output_dir" music \
        --work-dir "$work_dir" \
        --db "$db_path" \
        --force \
        --options '{"verbose": false}')"

    downloaded="$(jq '.downloaded' <<<"$result_json")"
    processed="$(jq '.processed' <<<"$result_json")"
    skipped="$(jq '.skipped' <<<"$result_json")"
    failed="$(jq '.failed' <<<"$result_json")"
    printf '%s downloaded, %s processed, %s skipped, %s failed\n' \
        "$downloaded" "$processed" "$skipped" "$failed"

    if [[ "$failed" -gt 0 ]]; then
        die "$failed failure(s) — check $output_dir for rescued raw files"
    fi
}

##==================================================================================================
##	MAIN
##==================================================================================================

main() {
    local playlist_url
    local real_script
    local project_dir

    playlist_url="$(readPlaylistUrl "$PLAYLIST_FILE")"
    real_script="$(readlink -f "$0")"
    project_dir="$(cd "${real_script%/*}/.." && pwd)"
    cd "$project_dir"
    processPlaylist "$playlist_url" "$OUTPUT_DIR" "$WORK_DIR" "$DB_PATH"
}

main
