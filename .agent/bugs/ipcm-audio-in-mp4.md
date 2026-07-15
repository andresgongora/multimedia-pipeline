---
title: Distorted audio in remove_silences output
summary: loudnorm upsampled to 192 kHz; downstream stages interpreted audio at 4× speed/wrong pitch. Also: auto-editor was emitting ipcm (raw PCM) in MP4 containers.
status: resolved
updated: 2026-06-25
---

# Bug: Distorted audio in remove_silences output

## Symptoms

`remove_silences_and_extract_clean_voice` pipeline output `.silences_removed.mp4` had:
- Garbled audio (extremely low-pitched, unintelligible — "slow motion" effect)
- Very low audio bitrate (~12 kbps AAC) in output
- Black screens / broken seeking in timeline

## Root Cause 1 — loudnorm 192 kHz upsample (primary)

`normalize_audio.py` ran `ffmpeg loudnorm` without `-ar`. The `loudnorm` filter upsamples
to 192 kHz internally for EBU R128 analysis and ffmpeg wrote the output at 192 kHz.

All downstream stages (remux_audio → auto-editor) received 192 kHz audio while the container
declared 48 kHz. auto-editor then encoded AAC at an absurdly low bitrate (~12 kbps) because
it estimated bitrate from the ratio of audio size to inflated sample count.

Result: audio played back at 4× speed with wrong pitch, completely unintelligible.

## Root Cause 2 — ipcm codec in MP4 (secondary)

`entrypoint.sh` forced `-c:a pcm_s16le` on auto-editor output. MP4 containers tag raw PCM as
`ipcm` (Apple in-place PCM), which most players cannot seek or decode correctly.

This was masked by Root Cause 1 — the audio was already unplayable for a different reason.

## Fix

**normalize_audio.py**: probe input sample rate, add `-ar <input_sr>` to ffmpeg command so
output stays at the original rate after loudnorm processing.

```python
_sr = next((int(s["sample_rate"]) for s in get_streams(src) if ...), 48000)
cmd = ["ffmpeg", ..., "-ar", str(_sr), str(dst)]
```

**entrypoint.sh**: removed `-c:a pcm_s16le`; replaced with format-aware codec selection:
forces `-c:a aac` for MP4/M4A/MOV outputs; lets auto-editor decide for WAV (defaults to pcm_s16le, correct).

## Tests Added

- `test/stages/normalize_audio.py` — `test_basic_normalize` now checks output sample rate matches input
- `test/stages/remove_silences.py` — `test_audio_codec_with_normalize` checks MP4 output codec is not raw PCM

## Verification

```bash
# After fix: normalize output at 48 kHz, not 192 kHz
ffprobe -v quiet -show_entries stream=sample_rate -of default output.wav
# → sample_rate=48000  (was 192000)

# After fix: MP4 output has AAC audio
ffprobe -v quiet -show_entries stream=codec_name,codec_tag_string -of default output.mp4
# → codec_name=aac, codec_tag_string=mp4a  (was pcm_s16le / ipcm)
```


# Bug: ipcm audio in MP4 output from remove_silences

## Symptom

`remove_silences_and_extract_clean_voice` pipeline output `.silences_removed.mp4` had:
- Garbled audio (extremely low-pitched, unintelligible)
- Black screens when seeking in timeline
- Extracted WAV also garbled

## Root Cause

Chain of two issues:

1. `stages/remove_silences/run.py` `_normalize_audio_in_video` calls `remux_audio` with default `audio_codec=pcm_s16le`. This produces a normalized temp video with raw PCM audio in MP4 (`ipcm` codec tag = Apple in-place PCM).

2. `stages/remove_silences/tools/silence-remover/entrypoint.sh` originally passed `-c:a pcm_s16le` to auto-editor explicitly. Even after removing that flag, auto-editor inherits the input codec from the normalized temp file (which is `pcm_s16le`).

Result: final output MP4 had `pcm_s16le` with `ipcm` codec tag. Most players can't decode this correctly in MP4 containers → garbled audio, broken seeking (no keyframe index compatible with `ipcm`).

## Fix

`entrypoint.sh`: detect output format and force `-c:a aac` for MP4/M4A/MOV containers. Let auto-editor decide for WAV (defaults to `pcm_s16le`, which is correct for WAV).

```bash
output_ext="${output##*.}"
output_ext_lower="${output_ext,,}"

ae_audio_codec_args=()
if [[ "$output_ext_lower" == "mp4" || "$output_ext_lower" == "m4a" || "$output_ext_lower" == "mov" ]]; then
  ae_audio_codec_args=("-c:a" "aac")
fi

auto-editor "$input" ... "${ae_audio_codec_args[@]}" ...
```

## Why Not Fix remux_audio Default?

`remux_audio` default `pcm_s16le` is intentional for lossless intermediates. Normalized temp video is never user-facing. Fixing at the entrypoint is simpler and more robust — the output codec is enforced regardless of intermediate codec chain.

## Testing

Added `test_audio_codec_with_normalize` to `test/stages/remove_silences.py`:
- Verifies MP4 output has non-PCM audio codec when `normalize=True`
- Also added codec check to `test_default_method` and `test_comparison_output`
- Codec check uses `shared/ffprobe.get_codec_names()` (not raw subprocess)

## Affected Pipelines

- `remove_silences_and_extract_clean_voice` — primary affected pipeline
- `scrub_youtube_podcast` — also calls `remove_silences` but with `.wav` output, unaffected

## Verification

```bash
ffprobe -v quiet -show_entries stream=codec_name,codec_tag_string -of default output.mp4
# Expected: codec_name=aac, codec_tag_string=mp4a
# Before fix: codec_name=pcm_s16le, codec_tag_string=ipcm
```
