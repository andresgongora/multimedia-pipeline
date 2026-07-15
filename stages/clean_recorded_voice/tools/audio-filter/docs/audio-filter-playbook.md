# Tutorial Voice Audio Filter Playbook

## Purpose

- Provide a repeatable, practical audio post-processing guide for narrated tutorial videos.
- Prioritize intelligibility and listener comfort over "radio voice" aesthetics.
- Keep processing stable across episodes so your channel sounds consistent.

## Recording Context (Project-Specific)

- Voice profile: male voice with a strong accent.
- Mic profile: low-cost clip-on lavalier (usable, but not premium detail/noise floor).
- Room profile: small furnished room, reduced reflections but still audible reverb tail.
- Production stage: this guide is for post-processing during video edit/export.
- Primary objective: maximize speech clarity and comprehension for explanations.
- Secondary objective: improve tone/aesthetics when it does not reduce clarity.

## Priority Stack (What Matters Most)

1. Intelligibility of words and consonants.
2. Consistent loudness across the full tutorial.
3. Reduced distractions (noise, pumping, harsh sibilance).
4. Natural, pleasant vocal tone.

## Goal

- Produce clear, consistent spoken-word audio for YouTube tutorials.
- Keep loudness steady when head movement changes mic distance.
- Avoid audible artifacts from over-processing.

## Loudness Policy (YouTube-Style Consistency)

- Integrated loudness target: `-14 LUFS`.
- True-peak ceiling: `-1 dBTP`.
- Keep loudness range controlled for tutorials: usually `LRA 5-8`.

### Why these targets

- `-14 LUFS` is a practical consistency target for tutorial content and aligns with typical platform-normalized playback behavior.
- `-1 dBTP` adds peak safety for transcoding and playback chain variations.
- `LRA 5-8` keeps narration expressive enough to sound human while reducing "volume riding" burden for viewers.

## Processing Order

1. Input cleanup (`highpass`, optional `adeclick`).
2. Noise control (`afftdn`, gentle `agate`).
3. Optional dereverb slot (disabled by default).
4. Tone shaping (`equalizer`, optional de-esser).
5. Dynamics control (`acompressor`).
6. Peak safety (`alimiter`).
7. Delivery loudness (`loudnorm`, preferably 2-pass).

### Why this order works

- Upstream cleanup prevents noise and low-frequency junk from triggering later dynamics stages.
- Dynamics and limiting are more predictable after tonal cleanup.
- Final loudness normalization should be last so delivery metrics are deterministic.

## Stage Reference

### 1) High-pass filter

- Purpose: remove rumble/handling noise and low-frequency HVAC content.
- Typical spoken-word range: `70-90 Hz` for male voice.
- Pros: quick clarity gain, less compressor overreaction to rumble.
- Cons: too aggressive can remove warmth.
- Risk if too high: voice thins out and loses body.
- Practical start: `highpass=f=75` and nudge to `80-85` only if rumble remains.

### 2) Declick (optional)

- Purpose: reduce short transients from taps/plastic clicks.
- Use when clicks are audible and distracting.
- Pros: reduces lav handling distraction without broad EQ changes.
- Cons: unnecessary use can soften articulation.
- Risk if too strong: can dull consonants.
- Practical start: keep conservative and bypass if clicks are not obvious.

### 3) Denoise

- Purpose: reduce constant background hiss/fan noise.
- Use light settings first.
- Pros: cleaner pauses, better perceived professionalism.
- Cons: strongest source of metallic "underwater" artifacts when overdone.
- Risk if too strong: metallic or watery artifacts.
- Practical start: set just enough to notice in pauses, then back off slightly.

### 4) Gate/Expander

- Purpose: lower room tone in pauses without abrupt dropouts.
- For tutorials, gentle downward expansion is preferred over hard gating.
- Pros: controls room tone and fan noise between phrases.
- Cons: aggressive settings create pumping/chatter and can clip syllable starts.
- Risk if too aggressive: chattering and audible pumping.
- Practical start: favor mild attenuation and smooth release over hard thresholding.

### 5) EQ / Notches

- Purpose: remove boxiness/harshness and improve clarity.
- Typical problem areas:

  - `200-500 Hz`: boxy/roomy buildup.
  - `2.5-5 kHz`: harshness and edge.
  - `5-8 kHz`: sibilance region (de-esser is often better than static deep cut).

- Pros: strongest lever for intelligibility tuning on accented narration.
- Cons: broad or deep cuts quickly sound unnatural.
- Risk if overdone: unnatural, hollow, or lispy voice.
- Practical start: small cuts (`1-3 dB`) and narrow-to-medium Q before any boosts.

### 6) De-esser (optional but useful)

- Purpose: control sharp `S`, `T`, `SH` without killing presence.
- Pros: improves long-form listening comfort.
- Cons: too much reduction masks consonant definition.
- Risk if too strong: lisping and dull speech.
- Practical start: reduce only occasional spikes, not every sibilant.

### 7) Compression

- Purpose: reduce level swings from head movement and performance changes.
- Spoken-word baseline start:

  - Threshold around `-18` to `-12 dB` equivalent.
  - Ratio around `2.5:1` to `4:1`.
  - Attack `5-20 ms`, release `100-180 ms`.

- Pros: stabilizes narration when mic distance varies.
- Cons: over-compression raises room tone and listener fatigue.
- Risk if too heavy: flat, fatiguing, noisy room tone.
- Practical start: target moderate gain reduction on peaks, not constant heavy reduction.

### 8) Limiter

- Purpose: catch overs and enforce peak ceiling.
- Typical ceiling: `-1 dB`.
- Pros: reliable true-peak safety.
- Cons: audible distortion if constantly hit.
- Risk if too hard: distortion/pumping.
- Practical start: limiter should catch occasional peaks, not work continuously.

### 9) Loudness normalization

- Purpose: consistent playback level across videos.
- Best approach: `loudnorm` two-pass for deterministic output.
- Pros: objective, repeatable final delivery.
- Cons: two-pass adds render time.
- Risk if single-pass only: less predictable integrated loudness.
- Practical start: keep two-pass for published exports; use faster previews only during rough edits.

## Preset Strategy: NATURAL vs BROADCAST vs future PODCAST

### NATURAL (current recommended default)

- Character: lighter processing, more vocal realism, less risk of artifacts.
- Best for: tutorial narration where clarity is primary but voice should still feel human.
- Tradeoff: less "locked" loudness compared with stronger chains.

### BROADCAST

- Character: tighter dynamics and steadier perceived loudness.
- Best for: noisy source, high movement, or when consistency is more important than natural tone.
- Tradeoff: easier to sound over-processed/fatiguing if pushed.

### PODCAST (future direction)

- Character target: natural but polished, slightly fuller than tutorial default.
- Typical shift from NATURAL: gentler high-mid cuts, careful low-mid warmth retention, moderate compression.
- Caution: optimize for intelligibility first, then add style.

## Decision Guide (Quick)

- If speech is understandable but slightly uneven: start with `natural`.
- If level swings and room tone are distracting: test `broadcast`.
- If planning long-form voice-led content: tune toward a `podcast` profile from `natural`, not from `broadcast`.

## Clarity-First Tuning for Accented Narration

- Emphasize consonant intelligibility carefully (`2-4 kHz` region), but avoid harshness.
- Control sibilance with de-essing before applying broad high-frequency cuts.
- Avoid excessive denoise/gating that smears syllable transitions.
- Prefer multiple small improvements over one aggressive stage.

## Small-Room Reverb Notes

- Furnished rooms reduce early reflections but usually leave short reverb tail and low-mid buildup.
- Current policy remains: no dedicated dereverb by default.
- Practical mitigation without dereverb:

  - Use moderate `200-500 Hz` cleanup.
  - Keep compression moderate to avoid lifting room tail.
  - Use gentle expansion to lower room tone between phrases.

## Tuning Workflow (Repeatable)

1. Start from `natural` preset.
2. Fix worst issue first (usually boxiness, hiss, or sibilance).
3. Render a short A/B segment (`20-40` seconds) before and after each change.
4. Check objective metrics (`I`, `TP`, `LRA`) and subjective clarity.
5. Keep only changes that improve comprehension without obvious artifacts.
6. Promote to broader pass only after short-segment validation.

## Quality Checklist Before Publish

- Speech remains easy to understand at low listening volume.
- No obvious pumping/chattering in pauses.
- Sibilants are controlled but consonants still crisp.
- Integrated loudness near `-14 LUFS`, true peak at or below `-1 dBTP`.
- No stage introduces metallic, phasey, or lispy artifacts.

## Mapping Your Current Shotcut Chain

- Keep: high-pass around `70 Hz`, corrective mid notch, compression/limiter, normalization.
- Improve: replace hard gate behavior with gentle expander settings.
- Add: `adeclick` and `deesser` in improved chain.
- Provision: dereverb slot included but disabled until tuned.
