---
title: Reference
summary: Shared modules API and component inventory.
updated: 2026-07-10
---

# Reference

## Shared Modules

### `shared/output.py` — Logging

Visual hierarchy: pipelines bold, stages indented/dim.

| Function | Purpose |
|----------|---------|
| `stage_header(name, input, output, config)` | Log input→output + config dict |
| `stage_log(name, msg)` | Stage-level log line (dim, indented) |
| `stage_timer(name, action)` | Context manager: times block, prints ✓ on exit |
| `pipeline_log(name, msg)` | Pipeline-level log line (bold) |
| `pipeline_timer(name, filename, verbose)` | Context manager: start/end with timing |

Example output:
```
scrub_youtube_media    → ◷ video.mp4
  identify             → ◷ video.mp4
  identify             → ✓ identified (2.1s)
  cut                  → ◷ video.mp4 → output.mp4
  cut                  → ✓ done (8.4s)
scrub_youtube_media    → ✓ video_clean.mp4 (45.2s)
```

### `shared/ffprobe.py` — Media Probing

Unified ffprobe wrappers. All stages use these instead of raw subprocess.

| Function | Returns | Notes |
|----------|---------|-------|
| `get_duration(path)` | `float \| None` | Duration in seconds, None on failure |
| `get_duration_strict(path)` | `float` | Raises RuntimeError on failure |
| `has_video_stream(path)` | `bool` | True if video stream exists |
| `get_streams(path)` | `list[dict]` | Raw stream info from ffprobe |
| `get_format(path)` | `dict` | Container format info |
| `get_format_and_streams(path)` | `tuple[dict, list]` | Both in one call |
| `get_tags(path)` | `dict` | Metadata tags, keys lowercased |
| `get_audio_bitrate(path)` | `int \| None` | Bits per second |
| `get_codec_names(path)` | `dict` | `{"video": "h264", "audio": "aac"}` |

### `shared/config.py` — Config Loading

| Function | Purpose |
|----------|---------|
| `deep_merge(base, override)` | Recursive dict merge |
| `load_config(default, custom, overrides)` | Cascade loader with deep merge |
| `propagate_verbose(cfg)` | Sets `verbose` in all `stages.*` sections |

Usage:
```python
cfg = load_config(_DEFAULT_CONFIG, config_path, options)
propagate_verbose(cfg)
stage_cfg = cfg.get("stages", {})
```

### `shared/io.py` — Output Path Handling

| Function | Purpose |
|----------|---------|
| `safe_output_path(input_file, requested)` | Validates output doesn't clobber input |

## Stages Inventory

| Stage | Type | Purpose |
|-------|------|---------|
| `scrub_metadata` | atomic | Strip all privacy-sensitive metadata via ffmpeg |
| `identify_youtube_media` | atomic | Find YouTube video ID from filename, comment tag, or yt-dlp search |
| `fetch_sponsorblock_timestamps` | atomic | Query SponsorBlock API for flagged segments |
| `cut` | atomic | Remove time segments via ffmpeg (precise or fast mode) |
| `convert_to_wav` | atomic | Convert primary audio stream to lossless WAV work audio |
| `normalize_audio` | atomic | Loudness normalization via ffmpeg loudnorm filter |
| `filter_podcast_audio` | atomic | Podcast intelligibility EQ/compress/gate chain |
| `remux_audio` | atomic | Replace audio track without re-encoding video |
| `add_metadata` | atomic | Embed metadata fields via ffmpeg stream copy |
| `suggest_name` | atomic | Generate clean filename from metadata |
| `extract_audio` | atomic | Extract audio track from video |
| `sanitize_video` | atomic | Warn/fix VFR and apply manual rotation before editing |
| `extract_and_clean_voice` | compound | extract_audio → clean_recorded_voice |
| `clean_recorded_voice/` | composite | Docker-based voice cleaning (audio-filter) |
| `remove_silences/` | composite | Docker-based silence removal (auto-editor) |

### Stage Details

#### `cut`

Modes:
- `precise` (default) — re-encodes, frame-accurate
- `fast` — stream copy, keyframe-accurate only

```python
from stages import cut
result = cut.run("video.mp4", "cut.mp4", [[10.0, 30.0], [90.0, 95.0]])
```

#### `identify_youtube_media`

Detection methods (in order):
1. Bracketed ID in filename: `video [dQw4w9WgXcQ].mp4`
2. Comment tag: `youtube:dQw4w9WgXcQ`
3. yt-dlp search (if enabled)

#### `filter_podcast_audio`

Filter chain: highpass → lowpass → corrective EQ → presence EQ → air cut
→ deesser → compressor → loudnorm → soxr resample

#### `remove_silences/`

Uses auto-editor in Docker. Options:
- `threshold` — silence detection threshold (linear amplitude)
- `margin` — padding around non-silent segments

Internal processing note:
- stage may run `normalize_audio` first when `normalize: true` so silence detection sees steadier levels
- this is intentional hidden prep, not a separate pipeline stage
- brutal honest take: keep it internal unless multiple pipelines need the exact same normalization policy before multiple different edit stages; pulling it out too early would spread coupling into pipelines and make stage contracts worse

#### `sanitize_video`

Pre-flight video prep stage. Default = warn on likely VFR, copy unchanged.
Optional fixes:
- `rotate` — physical pixel rotation in 90° steps
- `fix_framerate` + `target_fps` — transcode to CFR

#### `clean_recorded_voice/`

Uses audio-filter in Docker. DeepFilterNet-based noise reduction.

## Pipelines Inventory

| Pipeline | Description |
|----------|-------------|
| `scrub_youtube_media` | Identify → SponsorBlock → cut → metadata → suggest name |
| `scrub_youtube_podcast` | Above + silence removal + podcast filter + M4A output |
| `extract_and_clean_voice` | Video → cleaned WAV |
| `remove_silences_and_extract_clean_voice` | Video → trimmed video + cleaned WAV |

### Pipeline Stage Chains

#### `scrub_youtube_media`

```
input → scrub_metadata → identify_youtube_media → fetch_sponsorblock
      → cut → add_metadata → suggest_name → output
```

#### `scrub_youtube_podcast`

```
input → identify_youtube_media → fetch_sponsorblock
      → convert_to_wav → cut → remove_silences
      → filter_podcast_audio → scrub_metadata → add_metadata
      → suggest_name → output
```

#### `extract_and_clean_voice`

```
video → extract_audio → clean_recorded_voice → WAV
```

#### `remove_silences_and_extract_clean_voice`

```
video → sanitize_video → remove_silences → trimmed_video
                                        → extract_audio → clean_recorded_voice → WAV
```

## CLI Commands

| Command | Maps to |
|---------|---------|
| `scrub-youtube-media` | `pipelines/scrub_youtube_media.py` |
| `scrub-youtube-podcast` | `pipelines/scrub_youtube_podcast.py` |
| `extract-and-clean-voice` | `pipelines/extract_and_clean_voice.py` |
| `remove-silences-and-extract-clean-voice` | `pipelines/remove_silences_and_extract_clean_voice.py` |

## Config Files

| File | Purpose |
|------|---------|
| `pipelines/scrub_youtube_media.yaml` | Default config for scrub_youtube_media |
| `pipelines/scrub_youtube_podcast.yaml` | Default config for scrub_youtube_podcast |
| `pipelines/extract_and_clean_voice.yaml` | Default config for extract_and_clean_voice |
| `pipelines/remove_silences_and_extract_clean_voice.yaml` | Default config |

## Test Files

| Path | Purpose |
|------|---------|
| `test/sample/` | Input fixtures (gitignored) |
| `test/output/` | Output for manual comparison |
| `test/stages/<stage>.py` | Per-stage test script |

Run tests: `uv run test/stages/<stage>.py`
