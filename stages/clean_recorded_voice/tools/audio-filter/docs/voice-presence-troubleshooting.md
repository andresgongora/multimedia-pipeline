# Voice Presence Troubleshooting

## Symptom: Voice sounds "far away" instead of "in the head"

### What it means

"Far away" or "lacking intimacy" means the voice has lost its sense of closeness and proximity.
It sounds like someone speaking from across a room rather than directly into your ear.

### Primary causes (in order of likelihood)

#### 1. Artificial reverb/echo on the signal (`aecho`)

Any echo or reverb filter — even subtle — adds spatial depth, which the brain interprets as physical distance.
For tutorial voice that should feel intimate and present, echo is almost always wrong.
**Fix:** Remove `aecho` from the chain entirely.

#### 2. Presence region cuts (2.5–5 kHz)

The 2.5–5 kHz range is the *presence* region for voice. It is what makes a voice sound close,
forward, and "in your head". Cutting this range — even to reduce harshness — directly trades
intimacy for distance.
**Fix:** Replace presence cuts with a gentle boost around 3 kHz (+1 to +2 dB, wide Q ~4–5).
If harshness is still a problem, address it with the de-esser or a narrower cut above 5 kHz.

#### 3. AI noise suppression over-attenuation (DeepFilterNet)

High attenuation values (>20 dB) can strip subtle vocal textures — breath, lip movement, micro-dynamics —
that the brain uses as proximity cues. The voice becomes "too clean" and sounds processed/distant.
**Fix:** Keep `--dfn-atten-db` at 15–20 for voice. Go higher only if background noise is severe.

#### 4. Exciter frequency too high (`aexciter freq=`)

An exciter adds harmonic saturation above its crossover frequency. Setting it at 6 kHz adds
air and brilliance but does nothing for presence. Starting at 3–4 kHz adds warmth and closeness.
**Fix:** Lower `freq=` to ~3500 Hz to engage the presence range.

#### 5. Highpass cutoff too high

A highpass above 100 Hz removes chest resonance and proximity warmth that contribute to
the sense of a voice being physically close.
**Fix:** Keep highpass at 80–90 Hz, 12 dB/oct (p=2). Steeper slopes or higher cutoffs remove body.

---

## General presence/intimacy guidelines for tutorial voice

| Goal | Approach |
|---|---|
| More "in your head" | Gentle boost 2.5–3.5 kHz (+1–2 dB, Q 4–5) |
| Less harsh without losing presence | Narrow cut at 4–5 kHz, not at 3 kHz |
| More warmth/body | Low shelf boost at 150–200 Hz (+1.5–2 dB) |
| More air without distance | High shelf boost at 10–12 kHz (not reverb) |
| Reduce distance from bad room | Remove any echo/reverb filters; reduce DFN attenuation |

## Notes on low-quality source material

A mic that lacks proximity (off-axis, no proximity effect, small diaphragm) cannot have presence
*added back* through filtering alone — you can only avoid making it worse. Key rules:

- Never cut the presence region on an already-thin source.
- Do not add echo or room simulation.
- Keep DFN attenuation conservative.
- A gentle presence boost is better than cutting harshness at the cost of intimacy.
