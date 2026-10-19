"""Original ambient music beds, synthesized from oscillators with FFmpeg.

No samples or third-party recordings are used, so the result is fully owned,
free of Content ID claims, and deterministic: same settings, same file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .audio import MediaError, Tools

PAD_VERSION = "1"
# Root frequencies for a few dark-leaning keys; the pad is a minor chord with an added 9th.
KEYS = {"A": 110.0, "C": 130.81, "D": 146.83, "E": 82.41}
PULSE_SECONDS = 4.0  # a soft low pulse, like a slow heartbeat, every few seconds


def pad_expression(root: float) -> str:
    """aevalsrc expression: detuned minor-add9 chord with slow breathing, plus a low pulse."""
    third, fifth, ninth = root * 1.18921, root * 1.49831, root * 2.24492  # minor 3rd, 5th, 9th (+octave)
    voices = [
        (root, 0.050, 0.07), (root * 1.003, 0.040, 0.05),            # root, gently detuned pair
        (fifth, 0.032, 0.11), (root * 2, 0.026, 0.09),               # fifth and octave
        (third * 2, 0.020, 0.13), (ninth * 2, 0.010, 0.17),          # colour tones, quieter
    ]
    layers = [f"{amp}*(0.6+0.4*sin(2*PI*{lfo}*t))*sin(2*PI*{freq:.3f}*t)" for freq, amp, lfo in voices]
    pulse = f"0.09*sin(2*PI*{root / 2:.3f}*t)*exp(-2.5*mod(t,{PULSE_SECONDS}))"
    return "+".join(layers + [pulse])


def generate_pad(tools: Tools, out: Path, *, duration: float, key: str = "A", sample_rate: int = 48000) -> None:
    if key not in KEYS:
        raise MediaError(f"unknown key {key!r}; choose from {', '.join(KEYS)}")
    if not 5 <= duration <= 3600:
        raise MediaError("pad duration must be 5-3600 seconds")
    expr = pad_expression(KEYS[key])
    fade_out = max(duration - 4, 0)
    graph = (f"aevalsrc='{expr}':s={sample_rate}:d={duration:.3f}[pad];"
             f"anoisesrc=d={duration:.3f}:c=pink:r={sample_rate}:a=0.02:seed=7,lowpass=f=2500,highpass=f=300[air];"
             f"[pad][air]amix=inputs=2:normalize=0,lowpass=f=5000,"
             f"aecho=0.8:0.7:60|120:0.25|0.15,"
             f"afade=t=in:d=3,afade=t=out:st={fade_out:.3f}:d=4,"
             f"loudnorm=I=-24:TP=-3:LRA=7[out]")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".partial" + out.suffix)
    args = [tools.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-filter_complex", graph,
            "-map", "[out]", "-ac", "2", "-ar", str(sample_rate), "-c:a", "pcm_s16le", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:a", "+bitexact", str(tmp)]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=600, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError(f"music pad generation failed: {exc}") from exc
    if proc.returncode != 0:
        raise MediaError(f"music pad generation failed: {proc.stderr.strip()[-300:]}")
    tmp.replace(out)
