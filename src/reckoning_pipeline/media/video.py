"""Inspect rendered or source video with ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from .audio import MediaError, Tools


@dataclass(frozen=True)
class VideoInfo:
    duration_seconds: float
    width: int | None
    height: int | None
    frame_rate: float | None
    video_codec: str
    audio_codec: str
    pixel_format: str
    audio_sample_rate: int | None


def probe_video(tools: Tools, path: Path) -> VideoInfo:
    try:
        proc = subprocess.run([tools.ffprobe, "-v", "error", "-show_entries",
                               "stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,pix_fmt,sample_rate"
                               ":format=duration", "-of", "json", str(path)],
                              capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError(f"ffprobe failed: {exc}") from exc
    if proc.returncode != 0:
        raise MediaError(f"ffprobe could not read {path.name}: {proc.stderr.strip()[:200]}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    try:
        duration = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaError(f"no duration reported for {path.name}") from exc
    # Nominal rate; avg_frame_rate drifts slightly after concatenation.
    rate = v.get("r_frame_rate") or v.get("avg_frame_rate")
    fps = float(Fraction(rate)) if rate and rate != "0/0" else None
    return VideoInfo(round(duration, 3), v.get("width"), v.get("height"), round(fps, 3) if fps else None,
                     v.get("codec_name", ""), a.get("codec_name", ""), v.get("pix_fmt", ""),
                     int(a["sample_rate"]) if a.get("sample_rate") else None)
