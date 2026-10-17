"""Pure FFmpeg command construction for one scene, and for the final concat.

Commands are argument arrays. Filter graphs reference helper files (labels,
captions) by simple relative names, and FFmpeg runs with the scene's build
folder as its working directory, so no project path or text ever needs
filtergraph escaping.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..schemas.timeline import RenderProfile, TimelineScene, TimelineSegment
from ..schemas.visual import Motion

BG = "0x14161a"
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9/._-]+$")
LABEL_FONT_CANDIDATES = ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf",
                         "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
PUSH_ZOOM = 0.06   # slow push: zoom from 1.00 to 1.06 over the segment
PAN_ZOOM = 1.08    # pan: hold 1.08x and travel left to right


class CommandError(ValueError):
    """A scene can't be expressed safely as an FFmpeg command."""


def fps_arg(fps: float) -> str:
    return str(int(fps)) if float(fps).is_integer() else f"{fps:.3f}".rstrip("0")


def label_font() -> str:
    for candidate in LABEL_FONT_CANDIDATES:
        if Path(candidate).is_file() and SAFE_PATH_RE.match(candidate):
            return candidate
    raise CommandError("no usable font for on-screen labels; labelled visuals can't be rendered honestly")


def _fit(w: int, h: int) -> str:
    return (f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={BG},setsar=1")


def segment_filter(i: int, seg: TimelineSegment, profile: RenderProfile, label_file: str | None) -> str:
    w, h, fps = profile.width, profile.height, fps_arg(profile.fps)
    frames = max(int(round(seg.duration * profile.fps)), 1)
    if seg.motion is Motion.SLOW_PUSH:
        chain = (f"{_fit(2 * w, 2 * h)},zoompan=z='1+{PUSH_ZOOM}*on/{frames}':"
                 f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps},setsar=1")
    elif seg.motion is Motion.PAN:
        chain = (f"{_fit(2 * w, 2 * h)},zoompan=z='{PAN_ZOOM}':x='(iw-iw/zoom)*on/{frames}':"
                 f"y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={fps},setsar=1")
    else:
        chain = f"{_fit(w, h)},fps={fps}"
    if seg.kind == "video" and seg.source_duration is not None and seg.source_duration < seg.duration:
        chain += f",tpad=stop_mode=clone:stop_duration={seg.duration - seg.source_duration:.3f}"
    if label_file:
        size = max(h // 27, 14)
        chain += (f",drawtext=fontfile={label_font()}:textfile={label_file}:fontcolor=white:fontsize={size}:"
                  f"box=1:boxcolor=black@0.6:boxborderw={size // 2}:x=w-tw-{size * 2}:y={size * 2}")
    return f"[{i}:v]{chain},format=yuv420p,trim=duration={seg.duration:.3f},setpts=PTS-STARTPTS[v{i}]"


def scene_command(ffmpeg: str, scene: TimelineScene, profile: RenderProfile, output: str, *,
                  label_files: dict[str, str], captions_file: str | None) -> list[str]:
    fps = fps_arg(profile.fps)
    d = f"{scene.duration:.3f}"
    args = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning", "-y"]
    for seg in scene.segments:
        if seg.kind == "video":
            args += ["-i", seg.path]
        else:
            args += ["-loop", "1", "-framerate", fps, "-t", f"{seg.duration:.3f}", "-i", seg.path]
    audio_index = len(scene.segments)
    if scene.narration:
        args += ["-i", scene.narration.path]
    else:
        args += ["-f", "lavfi", "-t", d, "-i", f"anullsrc=r={profile.audio_sample_rate}:cl=stereo"]

    parts = [segment_filter(i, seg, profile, label_files.get(seg.beat_id)) for i, seg in enumerate(scene.segments)]
    joined = "".join(f"[v{i}]" for i in range(len(scene.segments)))
    video = f"{joined}concat=n={len(scene.segments)}:v=1:a=0"
    if scene.fade_in:
        video += f",fade=t=in:st=0:d={scene.fade_in:.3f}"
    if scene.fade_out:
        video += f",fade=t=out:st={scene.duration - scene.fade_out:.3f}:d={scene.fade_out:.3f}"
    if captions_file:
        # Opaque backing box keeps captions readable over any graphic.
        video += (f",subtitles={captions_file}:force_style='FontName=Helvetica,FontSize=16,BorderStyle=3,"
                  f"BackColour=&H99000000,Outline=6,Shadow=0,MarginV=18'")
    parts.append(video + "[vout]")

    audio = (f"[{audio_index}:a]aresample={profile.audio_sample_rate},"
             f"aformat=sample_fmts=fltp:channel_layouts=stereo")
    if scene.narration and scene.lead_in:
        audio += f",adelay={int(round(scene.lead_in * 1000))}:all=1"
    audio += f",apad,atrim=duration={d}"
    if scene.fade_in:
        audio += f",afade=t=in:st=0:d={scene.fade_in:.3f}"
    if scene.fade_out:
        audio += f",afade=t=out:st={scene.duration - scene.fade_out:.3f}:d={scene.fade_out:.3f}"
    parts.append(audio + "[aout]")

    args += ["-filter_complex", ";".join(parts), "-map", "[vout]", "-map", "[aout]",
             "-c:v", "libx264", "-preset", profile.video_preset, "-crf", str(profile.crf), "-pix_fmt", "yuv420p",
             "-r", fps, "-g", str(int(round(profile.fps * 2))), "-c:a", "aac", "-b:a", profile.audio_bitrate,
             "-ar", str(profile.audio_sample_rate), "-ac", "2", "-t", d, "-map_metadata", "-1",
             "-movflags", "+faststart", output]
    return args


def concat_list(paths: list[Path]) -> str:
    """Concat-demuxer list with each path single-quoted (quotes inside paths escaped)."""
    return "".join("file '" + str(p).replace("'", "'\\''") + "'\n" for p in paths)


def concat_command(ffmpeg: str, list_file: str, output: str) -> list[str]:
    return [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", "-map_metadata", "-1", "-movflags", "+faststart", output]
