"""Voice processing styles and named voice presets.

A *style* is an FFmpeg filter chain applied while narration is normalized
(TTS or human recordings alike). A *preset* bundles provider, voice, speed
and style under one name. Presets match a **style** (pace, pitch range,
processing), never a specific real person's voice.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

# The documentary chain, in order: rumble cut, low-mid warmth, "mud" cut, presence lift,
# gentle de-essing, 3:1 compression for an even confident level, a barely-there room,
# and a limiter at about -1.5 dBFS, leaving headroom for inter-sample (true) peaks.
VOICE_STYLES: dict[str, str] = {
    "none": "",
    "documentary": ("highpass=f=70,"
                    "equalizer=f=180:t=q:w=1.0:g=1.5,"
                    "equalizer=f=350:t=q:w=1.2:g=-1.5,"
                    "equalizer=f=4000:t=q:w=1.0:g=2.0,"
                    "deesser=i=0.35,"
                    "acompressor=threshold=-21dB:ratio=3:attack=6:release=120:makeup=2,"
                    "aecho=0.9:0.9:18:0.06,"
                    "alimiter=limit=0.84:level=disabled"),
}

# Tone match to the ANNT reference (references/ANNT/README.md), measured 2026-10-19: average
# 1/3-octave spectra of 3 min of ANNT vs 2 min of am_liam + documentary, level-aligned at
# 630-1600 Hz. About 60% of each difference is applied, because ANNT's music bed inflates its
# measurement (especially above 4 kHz). Mean band gap: 5.4 dB before, 2.5 dB after.
ANNT_MATCH_EQ = ("equalizer=f=250:t=o:w=0.7:g=2.5,"
                 "equalizer=f=400:t=o:w=0.7:g=4.5,"
                 "equalizer=f=630:t=o:w=0.7:g=2,"
                 "equalizer=f=1600:t=o:w=0.7:g=-2,"
                 "equalizer=f=2500:t=o:w=0.7:g=-3,"
                 "highshelf=f=4000:g=5")
_DOC = VOICE_STYLES["documentary"]
_SPLIT = _DOC.index("deesser")  # documentary EQ first, then the match EQ, then dynamics
VOICE_STYLES["annt"] = _DOC[:_SPLIT] + ANNT_MATCH_EQ + "," + _DOC[_SPLIT:]

# Tone match for Qwen3-TTS "Ryan" to a calm philosophy-documentary narrator, measured 2026-10-20:
# 1/3-octave spectra of 3 min of the reference vs Ryan's raw output, level-aligned at 630-1600 Hz.
# Ryan needs about +12 dB below 160 Hz (the reference's close-mic warmth) and more presence above
# 2.5 kHz; about 60% of each difference is applied, as for annt. Then the same dynamics as documentary.
SAGE_MATCH_EQ = ("highpass=f=60,"
                 "lowshelf=f=170:g=7,"
                 "equalizer=f=1000:t=o:w=0.7:g=-2,"
                 "highshelf=f=3000:g=5")
VOICE_STYLES["sage"] = SAGE_MATCH_EQ + "," + _DOC[_SPLIT:]


@dataclass(frozen=True)
class VoicePreset:
    name: str
    provider: str
    voice: str
    speed: float
    style: str
    description: str
    humanize: bool = False   # sentence-by-sentence synthesis with natural pauses (narration/humanize.py)
    instruct: str = ""       # delivery instruction, for engines that take one


# "reckoner" is the channel's house narrator. "annt" is kept as an alias so older commands and
# docs keep working; both give identical audio (the style, not the preset name, is fingerprinted).
_RECKONER = VoicePreset(
    name="reckoner", provider="voicebox", voice="kokoro:am_liam", speed=0.87, style="annt",
    description=("Reckoner, the house narrator. Style-matched to the ANNT reference (references/ANNT): adult male, "
                 "~133 Hz median pitch, ~165 words/min, steady documentary delivery, tone-matched EQ. Kokoro "
                 "am_liam (Apache-2.0) with documentary processing; not a clone of the reference narrator."),
)
SAGE_INSTRUCT = ("Speak as a calm, deep-voiced documentary narrator. Unhurried and reflective, warm and "
                 "intimate, with natural rises and falls, like telling a thoughtful story late at night.")
_SAGE = VoicePreset(
    name="sage", provider="voicebox", voice="qwen_custom_voice:Ryan", speed=1.0, style="sage", humanize=True,
    instruct=SAGE_INSTRUCT,
    description=("Calm, deep philosophy-documentary narration: ~120 Hz median pitch, wide natural intonation "
                 "(~11 semitones), reflective pace with sentence pauses, warm close-mic tone. Qwen3-TTS "
                 "CustomVoice 0.6B preset voice Ryan (Apache-2.0), humanized, with a style instruction; "
                 "not a clone of any narrator. About 10x slower than real time on this Mac."),
)
VOICE_PRESETS: dict[str, VoicePreset] = {
    "reckoner": _RECKONER,
    "sage": _SAGE,
    "annt": replace(_RECKONER, name="annt", description="Alias of 'reckoner'. " + _RECKONER.description),
}


class StyleError(ValueError):
    """Unknown style or preset."""


def style_filters(name: str) -> str:
    if name not in VOICE_STYLES:
        raise StyleError(f"unknown voice style {name!r}; available: {', '.join(VOICE_STYLES)}")
    return VOICE_STYLES[name]


def get_preset(name: str) -> VoicePreset:
    if name not in VOICE_PRESETS:
        raise StyleError(f"unknown voice preset {name!r}; available: {', '.join(VOICE_PRESETS)}")
    return VOICE_PRESETS[name]
