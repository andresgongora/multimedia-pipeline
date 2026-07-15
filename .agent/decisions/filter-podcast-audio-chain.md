---
title: filter_podcast_audio — filter chain tuning
summary: Documents A/B bench process and rationale for current default chain. Reference for future tuning.
status: active
updated: 2026-06-25
---

# filter_podcast_audio — filter chain decisions

## Current chain (as of 2026-06-25)

```
highpass=f=90
lowpass=f=14500
equalizer=f=200:t=q:w=1.0:g=-2         # mud cut
equalizer=f=3500:t=q:w=1.2:g=3.5       # presence boost
equalizer=f=8000:t=q:w=1.0:g=-1.5      # air cut
deesser=i=0.18:m=0.5:f=0.56
acompressor=threshold=-18dB:ratio=2.5:attack=8:release=120:knee=4:makeup=1
loudnorm=I=-14:LRA=7:TP=-2:print_format=none
aresample=resampler=soxr:precision=28
```

## How we got here

4 rounds of A/B bench. Script: `test/bench_audio_filter.py`. Two test files:
- `AI Is Discovering the Doorman Fallacy (128kbit_AAC-English).m4a` (~4 min)
- `Wearing the Wrong Hat in the 1920's Tales From the Bottle.m4a` (~8 min)

### Round 1 — 6 configs, full field

| Config | Time | Result |
|--------|------|--------|
| A_legacy | 31.6s | OK but not perfect |
| B_current | 51.7s | **Eliminated** — sounds bad |
| C_no_denoise | 43.8s | "Open" but harder to pick out in noise |
| D_lighter_comp | 44.1s | Bass heavy |
| E_presence | 46.1s | OK |
| F_fast | 41.9s | **Eliminated** — too much sibilance (confirmed by high TP) |

`afftdn` (denoiser) in B identified as main quality/speed problem — removes it in all subsequent rounds.

### Round 2 — A, D, E, F on second sample

D and E perceived as "bass heavy" vs A. Root cause: D/E use 250 Hz mud cut (higher center, preserves more low-mid) vs A's 200 Hz. Also neither cuts the 150–180 Hz chest resonance region.

### Round 3 — targeting bass heaviness

Variants G (deeper 200 Hz cut), H (dual 150+200 Hz cuts), I (A mud + E presence + deesser), J (I without deesser).

- G, H, I all "quite OK" — EQ differences subtle at these levels
- **I > J clearly** — deesser needed when presence boost is +3.5 dB
- I selected as new base: A mud profile (200 Hz -2 dB) + stronger presence (3500 Hz +3.5 dB) + deesser

### Round 4 — compressor variation on I base

| Config | ratio | attack | release | knee | Time | Verdict |
|--------|-------|--------|---------|------|------|---------|
| I_ref | 3 | 5 | 80 | 3 | 58.7s | reference |
| K_soft | 2 | 10 | 100 | 4 | 58.8s | — |
| L_hard | 4 | 3 | 60 | 2 | 46.5s | **Eliminated** — bad |
| M_punch | 3 | 15 | 60 | 3 | 49.9s | — |
| **N_smooth** | **2.5** | **8** | **120** | **4** | **60.0s** | **Winner — "nice, easy to listen to, still clean"** |

N chosen. Long release (120 ms) + gentle knee (4) = least pumping, most natural. Deesser keeps sibilance in check despite +3.5 dB presence.

## Key tradeoffs

- **afftdn removed** — adds ~8–20s, introduces watery artefacts on already-compressed podcast sources. Not worth it.
- **alimiter removed** — soxr resample + loudnorm TP=-2 sufficient. alimiter added latency overhead with no audible benefit on clean sources.
- **deesser kept** — essential when presence boost ≥ +3 dB. Removing it (J) clearly audible.
- **Presence at 3500 Hz not 3200 Hz** — 3500 Hz sits better for consonant clarity in noise; 3200 Hz felt "boxy" in comparison.
- **Long release (120 ms)** preferred — fast release (60 ms) causes pumping on natural speech pauses.

## Speed reference (8-min file)

| Chain | Time |
|-------|------|
| Legacy bash (A) | ~55s |
| Current (N) | ~60s |
| Old B_current | ~75s |

N costs ~5s more than legacy due to deesser. Acceptable.

## Future tuning notes

- If bass heaviness returns on a specific recording: try lowering `eq_mud_gain` to `-3` or adding a second cut at 150 Hz (H variant).
- If sibilance issue surfaces: increase `deesser_intensity` from 0.18 → 0.22 or `deesser_amount` from 0.5 → 0.6.
- If pumping heard on dense music podcast: increase `compressor_release` to 150 ms.
- Bench script reusable — add new chain function + entry in CONFIGS, re-run.
