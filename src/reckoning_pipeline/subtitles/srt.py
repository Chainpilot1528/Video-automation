"""SRT captions from approved narration text and measured narration audio.

Two timing methods, recorded honestly in each scene's ``caption_status``:

* ``approximate`` (default): each scene's cues span its measured speech
  (audio duration minus measured leading/trailing silence), and time is shared
  between cues in proportion to their character count. Good enough to review;
  individual cue boundaries can be off by a second or so.
* ``word_aligned``: a forced aligner supplies per-word timings and cues snap
  to them. No aligner ships yet; the interface is here for one to plug in.

Timing is on the narration timeline (scenes back to back). The Phase 7
timeline compiler re-times captions against the final edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

MAX_LINE_CHARS = 42
MAX_LINES = 2
MAX_CUE_CHARS = MAX_LINE_CHARS * MAX_LINES
MIN_CUE_SECONDS = 0.7
MAX_CUE_SECONDS = 7.0
MAX_CHARS_PER_SECOND = 20.0

_SENTENCE_RE = re.compile(r"(?<=[.!?…])[\"')\]]*\s+")
_CLAUSE_RE = re.compile(r"(?<=[,;:—–])\s+")
_TS_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$")


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str  # may contain one newline (two lines)


@dataclass(frozen=True)
class WordTiming:
    word: str
    start: float
    end: float


class ForcedAligner(Protocol):
    name: str

    def align(self, audio_path: Path, text: str) -> list[WordTiming]:
        """Return a timing for every word of ``text``, in order, relative to the audio start."""
        ...


@dataclass(frozen=True)
class SceneSpan:
    scene_id: str
    text: str
    offset: float            # scene start on the narration timeline
    speech_start: float      # relative to the scene start
    speech_end: float
    audio_path: Path | None = None


# --- text segmentation -------------------------------------------------------

def _wrap(text: str, width: int = MAX_LINE_CHARS) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _split_long(piece: str) -> list[str]:
    if len(piece) <= MAX_CUE_CHARS:
        return [piece]
    parts, out = _CLAUSE_RE.split(piece), []
    buf = ""
    for part in parts:
        candidate = f"{buf} {part}".strip()
        if len(candidate) <= MAX_CUE_CHARS:
            buf = candidate
            continue
        if buf:
            out.append(buf)
        if len(part) <= MAX_CUE_CHARS:
            buf = part
        else:  # no usable clause break: fall back to two-line word wrapping
            lines = _wrap(part)
            out += [" ".join(lines[i:i + MAX_LINES]) for i in range(0, len(lines), MAX_LINES)]
            buf = ""
    if buf:
        out.append(buf)
    return out


TINY_CUE_WORDS = 2   # a cue this short ("Or…", "Why?") would flash by; it joins a neighbour


def _merge_tiny(pieces: list[str]) -> list[str]:
    """Join one- or two-word pieces to the next piece (or the previous one at the end) when they fit."""
    out: list[str] = []
    i = 0
    while i < len(pieces):
        p = pieces[i]
        if len(p.split()) <= TINY_CUE_WORDS:
            if i + 1 < len(pieces) and len(p) + 1 + len(pieces[i + 1]) <= MAX_CUE_CHARS:
                pieces[i + 1] = f"{p} {pieces[i + 1]}"
                i += 1
                continue
            if out and len(out[-1]) + 1 + len(p) <= MAX_CUE_CHARS:
                out[-1] = f"{out[-1]} {p}"
                i += 1
                continue
        out.append(p)
        i += 1
    return out


def segment(text: str) -> list[str]:
    """Split narration into caption-sized pieces at sentence, then clause, then word boundaries;
    pieces of a word or two are joined to a neighbour so no caption flashes by."""
    pieces = []
    for sentence in _SENTENCE_RE.split(" ".join(text.split())):
        if sentence.strip():
            pieces += _split_long(sentence.strip())
    return _merge_tiny(pieces)


def layout(piece: str) -> str:
    return "\n".join(_wrap(piece))


# --- timing ------------------------------------------------------------------

def approximate_cues(span: SceneSpan) -> list[Cue]:
    pieces = segment(span.text)
    if not pieces:
        return []
    start, end = span.offset + span.speech_start, span.offset + span.speech_end
    total_chars = sum(len(p) for p in pieces)
    cues, t = [], start
    for i, p in enumerate(pieces):
        stop = end if i == len(pieces) - 1 else t + (end - start) * len(p) / total_chars
        cues.append(Cue(round(t, 3), round(stop, 3), layout(p)))
        t = stop
    return cues


def aligned_cues(span: SceneSpan, words: list[WordTiming]) -> list[Cue]:
    pieces = segment(span.text)
    counts = [len(p.split()) for p in pieces]
    if sum(counts) != len(words):
        raise ValueError(f"{span.scene_id}: aligner returned {len(words)} words for {sum(counts)} in the text")
    cues, i = [], 0
    for p, n in zip(pieces, counts):
        chunk = words[i:i + n]
        cues.append(Cue(round(span.offset + chunk[0].start, 3), round(span.offset + chunk[-1].end, 3), layout(p)))
        i += n
    return cues


# --- SRT text ----------------------------------------------------------------

def format_timestamp(seconds: float) -> str:
    ms = int(round(max(seconds, 0) * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_timestamp(text: str) -> float:
    m = _TS_RE.match(text.strip())
    if not m:
        raise ValueError(f"bad SRT timestamp {text!r}")
    h, mi, s, ms = map(int, m.groups())
    return h * 3600 + mi * 60 + s + ms / 1000


def to_srt(cues: list[Cue]) -> str:
    blocks = [f"{i}\n{format_timestamp(c.start)} --> {format_timestamp(c.end)}\n{c.text}"
              for i, c in enumerate(cues, 1)]
    return "\n\n".join(blocks) + "\n" if blocks else ""


def parse_srt(text: str) -> list[Cue]:
    cues = []
    for n, block in enumerate(re.split(r"\n\s*\n", text.replace("\r\n", "\n").strip()), 1):
        if not block.strip():
            continue
        lines = block.split("\n")
        if len(lines) < 3:
            raise ValueError(f"cue {n}: expected index, timing and text lines")
        if lines[0].strip() != str(n):
            raise ValueError(f"cue {n}: index is {lines[0].strip()!r}, expected {n}")
        try:
            start_s, end_s = lines[1].split("-->")
        except ValueError as exc:
            raise ValueError(f"cue {n}: bad timing line {lines[1]!r}") from exc
        cues.append(Cue(parse_timestamp(start_s), parse_timestamp(end_s), "\n".join(lines[2:])))
    return cues


def check_cues(cues: list[Cue]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a cue list."""
    errors, warnings = [], []
    for i, c in enumerate(cues, 1):
        if c.end <= c.start:
            errors.append(f"cue {i}: ends at or before it starts")
        if i > 1 and c.start < cues[i - 2].end - 0.001:
            errors.append(f"cue {i}: overlaps or precedes cue {i - 1}")
        if not c.text.strip():
            errors.append(f"cue {i}: empty text")
        lines = c.text.split("\n")
        if len(lines) > MAX_LINES:
            warnings.append(f"cue {i}: {len(lines)} lines (max {MAX_LINES})")
        if any(len(line) > MAX_LINE_CHARS for line in lines):
            warnings.append(f"cue {i}: line longer than {MAX_LINE_CHARS} characters")
        length = c.end - c.start
        if length > 0:
            if length < MIN_CUE_SECONDS:
                warnings.append(f"cue {i}: on screen only {length:.2f} s")
            if length > MAX_CUE_SECONDS:
                warnings.append(f"cue {i}: on screen {length:.1f} s (max {MAX_CUE_SECONDS:g})")
            cps = len(c.text.replace("\n", " ")) / length
            if cps > MAX_CHARS_PER_SECOND:
                warnings.append(f"cue {i}: {cps:.0f} characters/second is hard to read")
    return errors, warnings
