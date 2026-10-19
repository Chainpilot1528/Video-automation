"""Audio inspection and normalization with ffprobe/FFmpeg.

All commands are argument arrays (never shell strings). Measurements come
from the tools' own output; nothing here guesses a duration.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..config import PipelineConfig
from .tools import require_tool

NARRATION_CHANNELS = 1
EDGE_FADE_SECONDS = 0.01  # 10 ms fades at chunk edges prevent clicks at joins


class MediaError(RuntimeError):
    """FFmpeg/ffprobe failed or returned something unusable."""


@dataclass(frozen=True)
class Tools:
    ffmpeg: str
    ffprobe: str

    @classmethod
    def from_config(cls, config: PipelineConfig) -> "Tools":
        return cls(require_tool(config.ffmpeg_path, "PIPELINE_FFMPEG_PATH"),
                   require_tool(config.ffprobe_path, "PIPELINE_FFPROBE_PATH"))


@dataclass(frozen=True)
class AudioInfo:
    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str


@dataclass(frozen=True)
class LoudnessInfo:
    integrated_lufs: float | None
    true_peak_dbtp: float | None
    loudness_range_lu: float | None


@dataclass(frozen=True)
class SilenceInfo:
    leading_seconds: float
    trailing_seconds: float
    internal_gaps: list[tuple[float, float]] = field(default_factory=list)  # (start, duration)


def _run(args: list[str], timeout: float = 300) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError(f"{Path(args[0]).name} failed to run: {exc}") from exc
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-5:])
        raise MediaError(f"{Path(args[0]).name} exited {proc.returncode}: {tail}")
    return proc


def probe_audio(tools: Tools, path: Path) -> AudioInfo:
    proc = _run([tools.ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                 "stream=codec_name,sample_rate,channels:format=duration", "-of", "json", str(path)])
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise MediaError(f"{path.name} has no audio stream")
    s = streams[0]
    try:
        duration = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaError(f"ffprobe reported no duration for {path.name}") from exc
    return AudioInfo(round(duration, 3), int(s.get("sample_rate", 0)), int(s.get("channels", 0)),
                     s.get("codec_name", ""))


def normalize_audio(tools: Tools, src: Path, dst: Path, *, sample_rate: int, tempo: float = 1.0,
                    extra_filters: str = "") -> None:
    """Convert to mono 16-bit PCM WAV at the project rate, with click-free edges.

    ``tempo`` changes speaking speed without changing pitch (0.87 = 13% slower).
    ``extra_filters`` is an FFmpeg filter chain (a voice style) applied after resampling.
    Loudness is measured and reported, not altered here; the Phase 7 mix sets final levels.
    """
    if not 0.5 <= tempo <= 2.0:
        raise MediaError(f"tempo {tempo} is outside 0.5-2.0")
    info = probe_audio(tools, src)
    out_duration = info.duration_seconds / tempo
    fade_out_start = max(out_duration - EDGE_FADE_SECONDS, 0)
    speed = f"atempo={tempo:.4f}," if abs(tempo - 1.0) > 1e-6 else ""
    style = f"{extra_filters}," if extra_filters else ""
    filters = (f"{speed}aresample={sample_rate},{style}afade=t=in:d={EDGE_FADE_SECONDS},"
               f"afade=t=out:st={fade_out_start:.3f}:d={EDGE_FADE_SECONDS}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.stem + ".partial" + dst.suffix)
    _run([tools.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
          "-af", filters, "-ac", str(NARRATION_CHANNELS), "-ar", str(sample_rate), "-c:a", "pcm_s16le",
          "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact", str(tmp)])
    tmp.replace(dst)


_EBUR_RE = {
    "integrated_lufs": re.compile(r"Integrated loudness:\s*\n\s*I:\s*(-?[\d.]+|-inf)\s*LUFS"),
    "loudness_range_lu": re.compile(r"Loudness range:\s*\n\s*LRA:\s*(-?[\d.]+)\s*LU"),
    "true_peak_dbtp": re.compile(r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS"),
}


def measure_loudness(tools: Tools, path: Path) -> LoudnessInfo:
    proc = _run([tools.ffmpeg, "-nostdin", "-hide_banner", "-nostats", "-i", str(path),
                 "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = proc.stderr[proc.stderr.rfind("Summary:"):]
    values = {}
    for key, pattern in _EBUR_RE.items():
        m = pattern.search(summary)
        values[key] = None if not m or m.group(1) == "-inf" else float(m.group(1))
    return LoudnessInfo(**values)


_SIL_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SIL_END = re.compile(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)")


def detect_silence(tools: Tools, path: Path, duration: float, *, noise_db: float = -45.0,
                   min_seconds: float = 0.3) -> SilenceInfo:
    proc = _run([tools.ffmpeg, "-nostdin", "-hide_banner", "-nostats", "-i", str(path), "-af",
                 f"silencedetect=noise={noise_db}dB:d={min_seconds}", "-f", "null", "-"])
    starts = [max(float(x), 0.0) for x in _SIL_START.findall(proc.stderr)]
    ends = [(float(e), float(d)) for e, d in _SIL_END.findall(proc.stderr)]
    spans = []
    for i, start in enumerate(starts):
        end = ends[i][0] if i < len(ends) else duration  # silence running to the end has no end line
        spans.append((start, min(end, duration)))
    leading = trailing = 0.0
    gaps = []
    for start, end in spans:
        if start <= 0.01:
            leading = end
        elif end >= duration - 0.02:
            trailing = duration - start
        else:
            gaps.append((round(start, 3), round(end - start, 3)))
    if spans and spans[0][0] <= 0.01 and spans[0][1] >= duration - 0.02:
        leading, trailing, gaps = duration, duration, []  # entirely silent
    return SilenceInfo(round(leading, 3), round(trailing, 3), gaps)


def info_dict(*items) -> dict:
    out = {}
    for item in items:
        out.update(asdict(item))
    return out
