---
title: Wrapper Scripts
summary: Personal convenience shell scripts in wrapper_scripts/; symlinked into external folders to batch-process podcast/video libraries.
status: active
updated: 2026-07-15
---

# Wrapper Scripts

Shell scripts in `wrapper_scripts/` are meant to be **symlinked into external folders** (e.g. a podcast or video library). They are not part of the pipeline code — they are convenience entry points for recurring manual workflows.

Each script:

- Resolves its own location via the symlink, so it works from any folder
- Looks for an `Inbox/` subfolder next to the symlink for input files
- Writes output to a `YYYY.MM.DD/` subfolder (created automatically)
- Trashes originals on success, keeps them on failure

## Scripts

| Script | Pipeline | Input |
|---|---|---|
| `process_podcast_inbox.sh` | `scrub-youtube-podcast` | Audio files |
| `process_youtube_inbox.sh` | `scrub-youtube-media` | Video files |
| `process_recorded_videos.sh` | `extract-and-clean-voice` + `remove-silences-and-extract-clean-voice` | Recorded videos |

## Notes

- `process_recorded_videos.sh` accepts optional `--rotate 90|180|270`
- Rotate is forwarded to `sanitize_video` inside `remove_silences_and_extract_clean_voice`
