---
title: Multimedia Pipeline Frontier
summary: Present-tense repo boundary — Shape / Done / In progress / Next / Boundary.
status: active
updated: 2026-07-15
---

# Frontier

## Shape
- `pipelines/` — user-facing workflows; own orchestration, temp files, output naming
- `stages/` — reusable media ops; atomic, compound, or composite
- `shared/` — config, ffprobe, IO safety, output helpers
- `wrapper_scripts/` — personal convenience scripts; symlinked into external folders
- `test/stages/` — per-stage verification scripts; sample/output media gitignored
- `.agent/` — architecture, reference, bug logs, repo-state snapshot

## Done
- Repo published at https://github.com/andresgongora/multimedia-pipeline (MIT license)
- `scrub_youtube_podcast` runs edit path on WAV — `convert_to_wav -> cut -> remove_silences -> filter_podcast_audio`
- `filter_podcast_audio` preserves input sample rate after loudnorm
- `convert_to_wav` exists as reusable atomic stage

## In progress
- (none)

## Next
- Run one real `scrub_youtube_podcast` sample end-to-end — confirm speed gain and sound quality
- Decide if other audio pipelines want `convert_to_wav` reuse — only if real need appears
- Investigate whether silence-detection normalization should become a dedicated stage — keep inside `remove_silences` unless reused elsewhere

## Boundary

### Known risks
- `remove_silences` internal loudnorm pre-normalization is extra processing before final encode
- `filter_podcast_audio` presence boost can still expose source codec smear — next knob is `eq_presence_gain`

### Limitations
- No end-to-end automated test for `scrub_youtube_podcast` — pipeline result needs manual check
- Final podcast encode policy fixed by pipeline config — `m4a` + configured bitrate, not adaptive

### Deferred / discarded
- Hidden WAV conversion inside `cut` — discarded — dedicated stage cleaner
- Second early `filter_podcast_audio` pass in `scrub_youtube_podcast` — discarded — slower, likely worse audio
- Pull `normalize_audio` out of `remove_silences` — deferred — possible reuse upside but worse encapsulation unless more pipelines need it
