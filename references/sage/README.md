# sage: narration style reference

**What it is:** measurements of the narration in "Every Philosopher's Answer to Death | Iceberg Explained" by the YouTube channel *Philosophy Is Timeless*. The audio was supplied by the user on 2026-10-20 (17:14, MP3 320 kbps, sha256 `c3b28e233f05764e…`). It was analysed in place and **not copied into this repository**.

**Rights:** the audio belongs to its creator. It was used only to measure delivery and tone. Don't publish it, put it in renders, or use it to clone, fine-tune or imitate this narrator's voice; that would be impersonation, and it's against YouTube's rules.

**Measured style** (3 min from 1:00, plus spot checks at 0:00, 5:00 and 11:40):

| Property | Reference | How it was measured |
|---|---|---|
| Voice | adult male, deep | pitch analysis |
| Median pitch | about 118 Hz (p10–p90: 89–165 Hz) | autocorrelation on voiced frames |
| Intonation | about 11.5 semitones p10–p90, 4.3 st spread | pitch contour in semitones |
| Pauses | about 14 per minute, mostly 0.2–0.6 s, rarely over 1 s | silencedetect at -30 dB (the music bed fills pauses) |
| Loudness | -14.2 LUFS integrated, 3.2 LU range | EBU R128 |
| Tone | a strong low end (+11 to +16 dB at 100–200 Hz relative to the mids) | 1/3-octave average |
| Background | continuous quiet music bed | no pauses below -40 dB |

**How the pipeline matches the style** (not the voice): the `sage` preset, which is Qwen3-TTS CustomVoice 0.6B preset voice **Ryan** (Apache-2.0) with a calm-narrator instruction, sentence-by-sentence humanizing, and the `sage` tone-match EQ (60% of the measured difference).

**Comparison (2026-10-20, same original test passage, all humanized and tone-matched):**

| Voice | Pitch | Intonation range | Tone gap |
|---|---|---|---|
| Reference | 118 Hz | 11.5 st | 0 |
| **Qwen Ryan (chosen)** | 121 Hz | 11.4 st | 2.7 dB |
| Kokoro am_echo | 112 Hz | 10.3 st (6.0 before humanizing) | 2.1 dB |
| Kokoro am_puck | 119 Hz | 8.2 st | 2.0 dB |
| Qwen Aiden | 163 Hz | 14.0 st | 2.4 dB |

**Pipeline check (`narration build --preset sage`, 2026-10-20):** a 30-word demo scene took 2:26 to build (12.2 s of audio, about 12x real time). Results: intonation 11.7 st (reference 11.5), pitch movement 24.7 st/s (reference 24.9), sentence pauses 0.37-0.42 s, tone gap 2.3 dB, -21 LUFS, peak -4.8 dBFS, no warnings. The remaining low-end gap below 160 Hz is deliberate, since part of the reference's bass is its music bed.

