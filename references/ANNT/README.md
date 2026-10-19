# ANNT: narration style reference

**What it is:** a copy of the narration from "Why Big Companies Fail: The Smartphone Autopsy" by the YouTube channel *The Corporate Autopsy*. It was supplied by the user on 2026-10-18 and saved as `ANNT.mp3`: 10:19, MP3 at 320 kbps, sha256 `af01abc3b19f1b5c…`. The file is git-ignored and read-only.

**Rights:** the audio belongs to its creator. It's kept **only as a private listening and measurement reference**.
- Don't publish it, put it in renders, or commit it to git.
- Don't use it to clone, fine-tune or imitate this narrator's voice. That would be impersonation, and it's against YouTube's rules.

**Measured style** (90 s excerpt from 1:00, measured on 2026-10-18):

| Property | ANNT | How it was measured |
|---|---|---|
| Voice | adult male | pitch analysis |
| Median pitch | about 133 Hz (middle range 107–162 Hz) | autocorrelation on voiced frames |
| Pace | about 165 words/min (estimate) | syllable-envelope peaks ÷ 1.5 syllables/word |
| Loudness | -20.5 LUFS integrated, 3.7 LU range | EBU R128 |
| Background | continuous music bed under the voice | no pauses detected at -35 dB |

**How the pipeline matches the style** (not the voice): the `reckoner` voice preset (the house narrator; `annt` is an alias), which is Kokoro `am_liam` at speed 0.87 with the tone-matched `annt` style. See `docs/OPERATIONS.md`.

**Tone match (2026-10-19):** average 1/3-octave spectra of 3 min of ANNT vs 2 min of `am_liam` + documentary, level-aligned at 630–1600 Hz. About 60% of each difference is applied as EQ, because ANNT's music bed inflates its highs. The mean band gap fell from 5.4 dB to 2.5 dB. Remaining differences are mostly above 4 kHz, where ANNT's music sits and Kokoro has little energy.

**Overall mix match (episode preview 5):** -20.5 LUFS integrated with a 3.4 LU range. ANNT is -20.5 LUFS with 3.7 LU. The music bed sits about 10 dB below the voice in pauses.
