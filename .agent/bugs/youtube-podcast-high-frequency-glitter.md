---
title: High-frequency glitter in scrub_youtube_podcast output
summary: Investigation of codec-like sparkle on YouTube podcast speech. Main culprit: lossy AAC intermediate before precise cut caused extra lossy generation; filter sample rate also drifted upward after loudnorm.
status: resolved
updated: 2026-07-10
---

# Bug: high-frequency glitter in `scrub_youtube_podcast`

## Symptom

Final podcast output had small but audible high-frequency "glitter" / codec-like sparkle on speech.

Context:
- source often YouTube audio
- source itself already lossy, but subjectively "good enough"
- older podcast filter did not show this exact artifact as strongly
- recent pipeline changes improved issue, not fully gone

## Main finding

Biggest likely culprit not single EQ knob. Pipeline path had extra lossy generation mid-chain.

Old path:

```text
input
  -> filter_podcast_audio (AAC/M4A)
  -> cut precise (re-encode same codec)
  -> remove_silences (WAV)
  -> filter_podcast_audio (AAC/M4A)
  -> final
```

For AAC input after first filter pass, `cut` precise re-encoded already-filtered AAC again.

Observed reproduction on sample:
- first filtered file: AAC, `256 kb/s`, `96000 Hz`
- after `cut` precise: AAC, about `130 kb/s`, `96000 Hz`

That means effective path was close to:

```text
lossy source -> filtered AAC 256k -> cut AAC ~130k -> final AAC 256k
```

That is strong suspect for speech sparkle / codec grit.

## Secondary finding

`filter_podcast_audio` let ffmpeg write output at higher sample rate after `loudnorm`.

Reproduced on sample M4A:
- input: `44100 Hz`
- filtered output before fix: `96000 Hz`

Not proven root cause by itself, but bad intermediate for already-lossy podcast workflow. More resampling churn, no value.

## Filter-specific risk still present

Current filter still more artifact-revealing than legacy chain.

Relevant difference vs legacy:
- current presence boost `+3.5 dB` at `3500 Hz`
- legacy presence boost `+3 dB`
- current chain keeps deesser to control that lift

Conclusion: if artifact remains after codec-path fix, next suspect is presence tuning, not denoise. `afftdn` already removed earlier for watery artifacts.

## Fix

### 1. Remove early lossy generation from pre-edit work path

`pipelines/scrub_youtube_podcast.py`

- source audio is now converted to a dedicated WAV work file before any edits
- `cut` precise now operates on WAV, not AAC
- `remove_silences` also stays on WAV
- only one `filter_podcast_audio` pass remains, at the end, encoding final `.m4a`

New path:

```text
input
  -> convert_to_wav (WAV)
  -> cut precise (WAV)
  -> remove_silences (WAV)
  -> filter_podcast_audio (AAC/M4A)
  -> final
```

### 2. Preserve input sample rate in `filter_podcast_audio`

`stages/filter_podcast_audio.py`

- probe source audio sample rate with `get_streams()`
- add `-ar <input_sr>` to ffmpeg output command

## Verification

Stage test:

```bash
uv run test/stages/filter_podcast_audio.py
```

Passed. Confirmed:
- sample rate preserved: `48000 Hz -> 48000 Hz`
- loudness still near target: `-14.38 LUFS`
- true peak still safe: `-1.63 dBTP`

Pipeline-path reproduction after fix:
- first work file: WAV, `44100 Hz`
- cut output: WAV, `44100 Hz`
- final file: AAC, `44100 Hz`, about `249 kb/s`

No mid-pipeline AAC generation remains.

## Touch points

- `pipelines/scrub_youtube_podcast.py`
- `stages/filter_podcast_audio.py`
- `test/stages/filter_podcast_audio.py`

## If artifact still remains

Next safe experiment:
- lower `eq_presence_gain` from `3.5` to `3.0` or `2.5`

Reason:
- codec-path issue now reduced
- remaining glitter would more likely be presence emphasis exposing source codec smear
