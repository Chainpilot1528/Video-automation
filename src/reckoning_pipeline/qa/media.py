"""One FFmpeg pass over a finished render: loudness, true peak, silences, black and frozen picture.

Black and frozen detection are heuristics. A deliberate fade, a night shot or a
still photograph can trigger them, so they only ever raise warnings.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..media.audio import _EBUR_RE, Tools, _run
from ..schemas.qa import QAMeasurements

SILENCE_DB = -50.0     # quieter than this counts as silence (music beds sit well above it)
SILENCE_MIN = 3.0      # seconds
BLACK_MIN = 1.0        # seconds of near-black picture
FREEZE_MIN = 4.0       # seconds without visible change

_BLACK = re.compile(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)")
_FREEZE_START = re.compile(r"lavfi\.freezedetect\.freeze_start:\s*([\d.]+)")
_FREEZE_END = re.compile(r"lavfi\.freezedetect\.freeze_end:\s*([\d.]+)")
_SIL_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([\d.]+)")


def analysis_command(ffmpeg: str, path: Path) -> list[str]:
    # The picture is scaled down first: detection doesn't need full resolution, and it's much faster.
    return [ffmpeg, "-nostdin", "-hide_banner", "-nostats", "-i", str(path),
            "-vf", f"scale=320:-2,blackdetect=d={BLACK_MIN}:pix_th=0.10,"
                   f"freezedetect=n=0.003:d={FREEZE_MIN}",
            "-af", f"ebur128=peak=true,silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN}",
            "-f", "null", "-"]


def _pair(starts: list[float], ends: list[float], duration: float) -> list[tuple[float, float]]:
    out = []
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else duration  # still running at the end of the file
        out.append((round(max(start, 0.0), 3), round(max(end - start, 0.0), 3)))
    return out


def parse_analysis(stderr: str, duration: float) -> QAMeasurements:
    summary = stderr[stderr.rfind("Summary:"):]
    loud = {}
    for key, pattern in _EBUR_RE.items():
        m = pattern.search(summary)
        loud[key] = None if not m or m.group(1) == "-inf" else float(m.group(1))
    black = [(round(float(s), 3), round(float(e) - float(s), 3)) for s, e in _BLACK.findall(stderr)]
    # De-duplicate defensively: some FFmpeg builds log an event more than once.
    f_starts = list(dict.fromkeys(float(x) for x in _FREEZE_START.findall(stderr)))
    f_ends = list(dict.fromkeys(float(x) for x in _FREEZE_END.findall(stderr)))
    s_starts = [float(x) for x in _SIL_START.findall(stderr)]
    s_ends = [float(x) for x in _SIL_END.findall(stderr)]
    return QAMeasurements(duration_seconds=round(duration, 3), black_intervals=black,
                          frozen_intervals=_pair(f_starts, f_ends, duration),
                          silent_intervals=_pair(s_starts, s_ends, duration), **loud)


def analyse(tools: Tools, path: Path, duration: float) -> QAMeasurements:
    proc = _run(analysis_command(tools.ffmpeg, path), timeout=max(300.0, duration * 10))
    return parse_analysis(proc.stderr, duration)
