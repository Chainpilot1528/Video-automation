"""Humanized TTS: synthesize sentence by sentence and reassemble with natural pauses.

Reading one sentence at a time gives each its own intonation (a whole
paragraph in one request tends to flatten into a monotone). The pieces are
trimmed, given a small tempo drift and a measured pause, then joined over
very quiet room tone, so pauses don't drop to digital silence.

The pause pattern comes from measuring a calm documentary narrator: mostly
0.25-0.6 s between sentences, a little longer after questions, about 1 s
between paragraphs. Talking (rather than reading) also means uneven rhythm:
a held beat before a short, punchy line ("Hard work wins."), a breath after a
trailing ellipsis ("every rule… and wins anyway?"), and paragraph gaps that
vary. Everything is deterministic: the same text gives the same timing.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..media.audio import MediaError, Tools, probe_audio

HUMANIZE_VERSION = "3"  # bump when the assembly below changes its output
SENTENCE_GAPS = (0.42, 0.55, 0.33, 0.62, 0.38, 0.5, 0.45)
QUESTION_EXTRA = 0.15
PARAGRAPH_GAP = 0.95
PARAGRAPH_GAPS = (0.95, 1.1, 0.85, 1.0)  # varied, so paragraphs don't land like a metronome
ELLIPSIS_GAP = 0.5                        # after "every rule…", before "and wins anyway"
SHORT_LINE_WORDS = 4                      # a sentence this short is a punch line…
BEFORE_SHORT_EXTRA = 0.4                  # …so hold a little longer before it
JOIN_WORDS = 4                            # a statement this short is spoken together with the next sentence
EVEN_PACE_SLOW = 0.88                     # a piece slower than this share of the scene's pace…
EVEN_PACE_TARGET = 0.95                   # …is brought up to this share of it…
EVEN_PACE_MAX = 1.45                      # …but never sped up by more than this
TEMPO_DRIFT = (1.0, 1.02, 0.99, 1.01)   # multiplies the scene speed, sentence by sentence
ROOM_TONE_AMPLITUDE = 0.0015              # pink noise, about -60 dBFS RMS
TRIM_DB = -45                             # edge silence quieter than this is trimmed
WORK_RATE = 48000
_ABBREVIATIONS = ("Mr", "Mrs", "Ms", "Dr", "Prof", "St", "vs", "etc", "e.g", "i.e", "Jr", "Sr", "No")


@dataclass(frozen=True)
class Piece:
    text: str
    gap_after: float   # seconds of pause after this sentence (0 for the last one)
    tempo: float       # drift multiplier, applied on top of the scene speed


def split_sentences(text: str) -> list[str]:
    """Split on . ! ? (and an ellipsis) followed by space, without breaking common abbreviations."""
    out: list[str] = []
    buf = ""
    for part in re.split(r"(?<=[.!?…])\s+", text.strip()):
        buf = f"{buf} {part}".strip() if buf else part
        last_word = buf.rstrip(".").rsplit(" ", 1)[-1]
        if buf.endswith(".") and last_word in _ABBREVIATIONS:
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return [s for s in out if s.strip()]


def _join_short(sentences: list[str]) -> list[str]:
    """Speak a short statement together with the sentence after it ("Here's the situation. For three
    years…"): read alone, the voice drawls a few words. Questions, trailing ellipses and the paragraph's
    last sentence stay on their own, because their pause is deliberate."""
    out: list[str] = []
    i = 0
    while i < len(sentences):
        s = sentences[i]
        if (i + 1 < len(sentences) and len(s.split()) <= JOIN_WORDS
                and not s.endswith(("?", "…", "...", "!"))):
            out.append(f"{s} {sentences[i + 1]}")
            i += 2
            continue
        out.append(s)
        i += 1
    return out


def plan_pieces(text: str) -> list[Piece]:
    """Sentences (short ones joined to the next) with their pauses. Paragraphs are separated by blank lines."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    pieces: list[Piece] = []
    n = 0
    for pi, para in enumerate(paragraphs):
        sentences = _join_short(split_sentences(" ".join(para.split())))
        for si, sentence in enumerate(sentences):
            last_in_para = si == len(sentences) - 1
            if last_in_para:
                gap = PARAGRAPH_GAPS[pi % len(PARAGRAPH_GAPS)]
            elif sentence.endswith(("…", "...")):
                gap = ELLIPSIS_GAP
            else:
                gap = SENTENCE_GAPS[n % len(SENTENCE_GAPS)]
                if sentence.endswith("?"):
                    gap += QUESTION_EXTRA
                if len(sentences[si + 1].split()) <= SHORT_LINE_WORDS:
                    gap += BEFORE_SHORT_EXTRA
            pieces.append(Piece(sentence, gap, TEMPO_DRIFT[n % len(TEMPO_DRIFT)]))
            n += 1
    if pieces:
        pieces[-1] = Piece(pieces[-1].text, 0.0, pieces[-1].tempo)  # the scene's hold handles the end
    return pieces


def syllables(text: str) -> int:
    """A rough syllable count (vowel groups), enough to compare how fast pieces are spoken."""
    total = 0
    for word in re.findall(r"[A-Za-z']+", text):
        w = word.lower().replace("'", "")
        n = len(re.findall(r"[aeiouy]+", w))
        if w.endswith("e") and not w.endswith(("le", "ee")) and n > 1:
            n -= 1
        total += max(n, 1)
    return max(total, 1)


def pace_boosts(pieces: list[Piece], rates: list[float]) -> list[float]:
    """Tempo multipliers that lift drawn-out pieces toward the scene's own pace (never slower, at most
    EVEN_PACE_MAX). The pace is the median of the longer pieces, which the voice reads naturally."""
    long_rates = [r for p, r in zip(pieces, rates) if len(p.text.split()) >= 7] or rates
    ref = sorted(long_rates)[len(long_rates) // 2]
    return [min(max(ref * EVEN_PACE_TARGET / r, 1.0), EVEN_PACE_MAX) if r < ref * EVEN_PACE_SLOW else 1.0
            for r in rates]


def settings_key() -> dict:
    """Everything that shapes the output, for narration fingerprints."""
    return {"humanize": HUMANIZE_VERSION, "gaps": SENTENCE_GAPS, "question_extra": QUESTION_EXTRA,
            "paragraph_gap": PARAGRAPH_GAP, "paragraph_gaps": PARAGRAPH_GAPS,
            "ellipsis_gap": ELLIPSIS_GAP, "short_line": [SHORT_LINE_WORDS, BEFORE_SHORT_EXTRA], "join": JOIN_WORDS,
            "even_pace": [EVEN_PACE_SLOW, EVEN_PACE_TARGET, EVEN_PACE_MAX], "drift": TEMPO_DRIFT, "room": ROOM_TONE_AMPLITUDE, "trim": TRIM_DB}


def _ffmpeg(tools: Tools, args: list[str], what: str) -> None:
    try:
        proc = subprocess.run([tools.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y", *args],
                              capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError(f"{what}: FFmpeg failed to run ({exc})") from exc
    if proc.returncode != 0:
        raise MediaError(f"{what}: {proc.stderr.strip()[-300:]}")


def humanized_tts(tools: Tools, synthesize: Callable[[str, Path], None], text: str, out: Path, *,
                  speed: float, work_dir: Path) -> list[tuple[str, float, float]]:
    """Synthesize ``text`` piece by piece with ``synthesize(sentence, path)`` and write one WAV to ``out``.

    The result is at the final tempo already, so normalize it with tempo 1.0. Returns where each
    sentence's speech starts and ends in the file: (sentence, start, end) in seconds.
    """
    pieces = plan_pieces(text)
    if not pieces:
        raise MediaError("nothing to synthesize")
    trim = f"silenceremove=start_periods=1:start_threshold={TRIM_DB}dB"
    raws, rates = [], []
    for i, piece in enumerate(pieces):
        raw = work_dir / f"s{i:03d}.aiff"  # providers write WAV or AIFF; FFmpeg probes the content
        synthesize(piece.text, raw)
        clean = work_dir / f"c{i:03d}.wav"
        _ffmpeg(tools, ["-i", str(raw), "-af", f"aformat=channel_layouts=mono,{trim},areverse,{trim},areverse,"
                        f"aresample={WORK_RATE}", "-ac", "1", "-ar", str(WORK_RATE), "-c:a", "pcm_s16le", str(clean)],
                f"sentence {i + 1}")
        raws.append(clean)
        rates.append(syllables(piece.text) / max(probe_audio(tools, clean).duration_seconds, 0.05))
    boost = pace_boosts(pieces, rates)
    parts = []
    timings: list[tuple[str, float, float]] = []
    clock = 0.0
    for i, piece in enumerate(pieces):
        tempo = min(max(speed * piece.tempo * boost[i], 0.5), 2.0)
        part = work_dir / f"p{i:03d}.wav"
        _ffmpeg(tools, ["-i", str(raws[i]), "-af", f"atempo={tempo:.4f},aresample={WORK_RATE},apad=pad_dur={piece.gap_after:.3f}",
                        "-ac", "1", "-ar", str(WORK_RATE), "-c:a", "pcm_s16le", str(part)], f"sentence {i + 1} pace")
        parts.append(part)
        length = probe_audio(tools, part).duration_seconds
        speech = max(length - piece.gap_after, 0.0)
        timings.append((piece.text, round(clock, 3), round(clock + speech, 3)))
        clock += length
    listing = work_dir / "parts.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    joined = work_dir / "joined.wav"
    _ffmpeg(tools, ["-f", "concat", "-safe", "0", "-i", str(listing), "-c:a", "pcm_s16le", str(joined)], "join")
    duration = probe_audio(tools, joined).duration_seconds
    # Room tone under everything: pauses sound like a quiet room, not a cut-out.
    _ffmpeg(tools, ["-i", str(joined), "-filter_complex",
                    f"anoisesrc=color=pink:amplitude={ROOM_TONE_AMPLITUDE}:r={WORK_RATE}:seed=7:d={duration:.3f}[room];"
                    "[0:a][room]amix=inputs=2:normalize=0:duration=first[out]",
                    "-map", "[out]", "-ac", "1", "-ar", str(WORK_RATE), "-c:a", "pcm_s16le", str(out)],
            "room tone")
    return timings
