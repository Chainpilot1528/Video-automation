"""When each word of an on-screen quote should appear: in step with the narrator reading it.

The quote is located inside the scene's narration text (word by word, ignoring case and
punctuation). Each matched word's position in the text is turned into a time:

* exactly to the sentence, when the narration was humanized (the build records where
  every sentence starts and ends), with words spread by character count inside it;
* otherwise across the measured speech span, by character count.

If the quote isn't read aloud in this scene, the words are paced evenly instead and the
caller gets a warning. Times are returned relative to the beat's start.
"""

from __future__ import annotations

import re

from ..narration.humanize import plan_pieces
from ..schemas.narration import ChunkReport

EVEN_WORDS_PER_SECOND = 2.6   # pacing when the quote isn't in the narration
_WORD = re.compile(r"\S+")


def _norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower())


def _tokens(text: str) -> list[tuple[str, int]]:
    """(normalized word, char offset) for each word; words that are only punctuation are dropped."""
    out = []
    for m in _WORD.finditer(text):
        n = _norm(m.group())
        if n:
            out.append((n, m.start()))
    return out


def find_quote(quote: str, narration: str) -> list[int] | None:
    """Char offsets (in whitespace-collapsed ``narration``) of each word of ``quote``, or None."""
    q = [n for n, _ in _tokens(quote)]
    t = _tokens(narration)
    if not q:
        return None
    words = [n for n, _ in t]
    for i in range(len(words) - len(q) + 1):
        if words[i:i + len(q)] == q:
            return [t[i + k][1] for k in range(len(q))]
    return None


def audio_time(offset: int, narration: str, chunk: ChunkReport) -> float:
    """Seconds into the narration file at which the character at ``offset`` is spoken."""
    pieces = [p.text for p in plan_pieces(narration)]
    if chunk.sentences and len(chunk.sentences) == len(pieces):
        pos = 0
        for piece, s in zip(pieces, chunk.sentences):
            start = narration.find(piece, pos)
            if start < 0:
                break
            end = start + len(piece)
            if offset < end:
                frac = min(max((offset - start) / max(len(piece), 1), 0.0), 1.0)
                return s.start + (s.end - s.start) * frac
            pos = end
    speech_start = min(chunk.leading_silence_seconds, chunk.duration_seconds)
    speech_end = max(chunk.duration_seconds - chunk.trailing_silence_seconds, speech_start)
    return speech_start + (speech_end - speech_start) * min(max(offset / max(len(narration), 1), 0.0), 1.0)


def word_times(text: str, narration_text: str, chunk: ChunkReport | None, *, lead_in: float, beat_start: float,
               layer_start: float) -> tuple[list[float], str | None]:
    """Beat-relative start time for each whitespace-separated word of ``text``, and a warning if any."""
    words = text.split()
    narration = " ".join(narration_text.split())
    offsets = find_quote(text, narration) if chunk is not None and narration else None
    if offsets is None:
        times = [round(layer_start + i / EVEN_WORDS_PER_SECOND, 3) for i in range(len(words))]
        why = "no measured narration for this scene" if chunk is None else "the quote isn't read in this scene"
        return times, f"{why}; its words are paced evenly"
    times: list[float] = []
    k = 0
    for word in words:
        if _norm(word) and k < len(offsets):
            t = lead_in + audio_time(offsets[k], narration, chunk) - beat_start
            k += 1
        else:
            t = times[-1] if times else layer_start  # punctuation-only "words" follow their neighbour
        times.append(round(max(t, layer_start), 3))
    for i in range(1, len(times)):  # never reveal out of reading order
        times[i] = max(times[i], times[i - 1])
    return times, None
