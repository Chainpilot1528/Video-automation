"""Humanized TTS: synthesize sentence by sentence and reassemble with natural pauses.

Reading one sentence at a time gives each its own intonation (a whole
paragraph in one request tends to flatten into a monotone). The pieces are
trimmed, given a small tempo drift and a measured pause, then joined over
very quiet room tone, so pauses don't drop to digital silence.

The pause pattern comes from measuring a calm documentary narrator: mostly
0.25-0.6 s between sentences, a little longer after questions, about 1 s
between paragraphs. Everything is deterministic: the same text gives the
same timing.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..media.audio import MediaError, Tools, probe_audio

HUMANIZE_VERSION = "1"  # bump when the assembly below changes its output
SENTENCE_GAPS = (0.42, 0.55, 0.33, 0.62, 0.38, 0.5, 0.45)
QUESTION_EXTRA = 0.15
PARAGRAPH_GAP = 0.95
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


def plan_pieces(text: str) -> list[Piece]:
    """Sentences with their pauses. Paragraphs are separated by blank lines."""
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    pieces: list[Piece] = []
    n = 0
    for pi, para in enumerate(paragraphs):
        sentences = split_sentences(" ".join(para.split()))
        for si, sentence in enumerate(sentences):
            last_in_para = si == len(sentences) - 1
            gap = PARAGRAPH_GAP if last_in_para else SENTENCE_GAPS[n % len(SENTENCE_GAPS)]
            if sentence.endswith("?") and not last_in_para:
                gap += QUESTION_EXTRA
            pieces.append(Piece(sentence, gap, TEMPO_DRIFT[n % len(TEMPO_DRIFT)]))
            n += 1
    if pieces:
        pieces[-1] = Piece(pieces[-1].text, 0.0, pieces[-1].tempo)  # the scene's hold handles the end
    return pieces


def settings_key() -> dict:
    """Everything that shapes the output, for narration fingerprints."""
    return {"humanize": HUMANIZE_VERSION, "gaps": SENTENCE_GAPS, "question_extra": QUESTION_EXTRA,
            "paragraph_gap": PARAGRAPH_GAP, "drift": TEMPO_DRIFT, "room": ROOM_TONE_AMPLITUDE, "trim": TRIM_DB}


def _ffmpeg(tools: Tools, args: list[str], what: str) -> None:
    try:
        proc = subprocess.run([tools.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y", *args],
                              capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError(f"{what}: FFmpeg failed to run ({exc})") from exc
    if proc.returncode != 0:
        raise MediaError(f"{what}: {proc.stderr.strip()[-300:]}")


def humanized_tts(tools: Tools, synthesize: Callable[[str, Path], None], text: str, out: Path, *,
                  speed: float, work_dir: Path) -> None:
    """Synthesize ``text`` piece by piece with ``synthesize(sentence, path)`` and write one WAV to ``out``.

    The result is at the final tempo already, so normalize it with tempo 1.0.
    """
    pieces = plan_pieces(text)
    if not pieces:
        raise MediaError("nothing to synthesize")
    parts = []
    for i, piece in enumerate(pieces):
        raw = work_dir / f"s{i:03d}.aiff"  # providers write WAV or AIFF; FFmpeg probes the content
        synthesize(piece.text, raw)
        tempo = min(max(speed * piece.tempo, 0.5), 2.0)
        trim = f"silenceremove=start_periods=1:start_threshold={TRIM_DB}dB"
        part = work_dir / f"p{i:03d}.wav"
        _ffmpeg(tools, ["-i", str(raw), "-af",
                        f"aformat=channel_layouts=mono,{trim},areverse,{trim},areverse,"
                        f"atempo={tempo:.4f},aresample={WORK_RATE},apad=pad_dur={piece.gap_after:.3f}",
                        "-ac", "1", "-ar", str(WORK_RATE), "-c:a", "pcm_s16le", str(part)],
                f"sentence {i + 1}")
        parts.append(part)
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
