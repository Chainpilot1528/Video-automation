"""Execute a timeline plan: per-scene renders (cached), concat, validate, promote, report.

* A scene is reused only if a render with its exact input fingerprint exists
  and still probes correctly; modification times are never trusted.
* Every output is written to a temporary path, checked with ffprobe, then
  atomically renamed into place. Finished renders are named by fingerprint,
  so nothing is ever overwritten.
* On failure, logs and intermediates are kept, and a failed render report is
  written; re-running resumes from the scenes that already succeeded.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from ..media.audio import MediaError, Tools
from ..media.video import VideoInfo, probe_video
from ..project.validate import ValidationResult
from ..schemas import SceneManifest
from ..schemas.render import RenderInput, RenderOutcome, RenderOutput, RenderReport
from ..schemas.timeline import TimelinePlan, TimelineScene
from ..subtitles.srt import Cue, check_cues, to_srt
from ..timeline.compiler import compile_timeline
from ..utils.fs import safe_resolve, sha256_file, write_json_atomic, write_text_atomic
from ..visuals.placeholders import placeholder_svg_text
from .commands import concat_command, concat_list, scene_command
from .profiles import get_profile

RENDERS_DIR = "renders"
SCENE_TOLERANCE = 0.1           # seconds a scene render may differ from its planned duration
SCENE_TIMEOUT_FACTOR = 60       # allow up to 60 s of wall time per second of scene
GIB = 1024**3
EST_BITRATE = {"preview": 1.5e6, "master_16x9": 8e6}  # bits/s, for the disk-space check


class RenderError(RuntimeError):
    """Rendering failed; details are in the log and render report."""


@dataclass
class RenderResult:
    plan: TimelinePlan
    output: Path | None = None
    captions: Path | None = None
    report_path: Path | None = None
    rendered: list[str] = field(default_factory=list)
    cached: list[str] = field(default_factory=list)
    final_cached: bool = False


def ffmpeg_version(tools: Tools) -> str:
    proc = subprocess.run([tools.ffmpeg, "-version"], capture_output=True, text=True, timeout=60, check=False)
    return (proc.stdout.splitlines() or ["unknown"])[0]


def plan_render(result: ValidationResult, tools: Tools, profile_name: str, *, media_root: Path | None = None,
                burn_captions: bool = False) -> tuple[TimelinePlan, Path]:
    profile = get_profile(profile_name, result.manifest)
    base = safe_resolve(result.project_dir, f"{RENDERS_DIR}/{profile.name}")
    plan = compile_timeline(result, profile, ffmpeg_version=ffmpeg_version(tools),
                            placeholder_dir=base / "build" / "placeholders",
                            probe_video=lambda p: probe_video(tools, p).duration_seconds,
                            media_root=media_root, burn_captions=burn_captions)
    report = safe_resolve(result.project_dir, f"reports/timeline-{profile.name}.json")
    report.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(report, plan.model_dump(mode="json"))
    return plan, base


def render(result: ValidationResult, tools: Tools, profile_name: str, *, media_root: Path | None = None,
           burn_captions: bool = False, min_free_gb: float = 0.0, dry_run: bool = False) -> RenderResult:
    started = datetime.now(timezone.utc)
    plan, base = plan_render(result, tools, profile_name, media_root=media_root, burn_captions=burn_captions)
    out = RenderResult(plan)
    if dry_run:
        return out
    _check_disk(base, plan, min_free_gb)
    for sub in ("scenes", "build", "logs"):
        (base / sub).mkdir(parents=True, exist_ok=True)

    commands: list[list[str]] = []
    scene_files: list[Path] = []
    try:
        for scene in plan.scenes:
            target = base / "scenes" / f"{scene.scene_id}-{scene.fingerprint[:16]}.mp4"
            if _scene_ok(tools, target, scene):
                out.cached.append(scene.scene_id)
            else:
                commands.append(_render_scene(tools, plan, scene, base, target))
                out.rendered.append(scene.scene_id)
            scene_files.append(target)

        stem = f"{plan.project_id}-{plan.profile.name}-{plan.fingerprint[:12]}"
        final = base / f"{stem}.mp4"
        if final.exists() and _final_ok(tools, final, plan):
            out.final_cached = True
        else:
            commands.append(_concat(tools, base, scene_files, final, plan))
        out.output = final
        out.captions = _write_sidecar(plan, base / f"{stem}.srt")
        _record_final_durations(result, plan)
        info = probe_video(tools, final)
        out.report_path = _write_report(result, plan, started, RenderOutcome.SUCCEEDED, commands, final, info, [])
    except (RenderError, MediaError) as exc:
        out.report_path = _write_report(result, plan, started, RenderOutcome.FAILED, commands, None, None, [str(exc)])
        raise RenderError(f"{exc}\nRender report: {out.report_path}") from exc
    return out


def _check_disk(base: Path, plan: TimelinePlan, min_free_gb: float) -> None:
    need = plan.total_duration * EST_BITRATE[plan.profile.name] / 8 * 2  # scene files + final
    probe = base
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free - need < min_free_gb * GIB:
        raise RenderError(f"not enough disk space: {free / GIB:.1f} GiB free, render needs ~{need / GIB:.2f} GiB "
                          f"plus the {min_free_gb:g} GiB margin")


def _scene_ok(tools: Tools, path: Path, scene: TimelineScene) -> bool:
    if not path.is_file():
        return False
    try:
        info = probe_video(tools, path)
    except MediaError:
        return False
    return abs(info.duration_seconds - scene.duration) <= SCENE_TOLERANCE and bool(info.audio_codec)


def _final_ok(tools: Tools, path: Path, plan: TimelinePlan) -> bool:
    try:
        info = probe_video(tools, path)
    except MediaError:
        return False
    return _final_problems(info, plan) == []


def _final_problems(info: VideoInfo, plan: TimelinePlan) -> list[str]:
    p = plan.profile
    problems = []
    tolerance = 0.05 * len(plan.scenes) + 0.2  # AAC frame padding at each join
    if abs(info.duration_seconds - plan.total_duration) > tolerance:
        problems.append(f"duration {info.duration_seconds:.2f} s, expected {plan.total_duration:.2f} s")
    if (info.width, info.height) != (p.width, p.height):
        problems.append(f"size {info.width}x{info.height}, expected {p.width}x{p.height}")
    if info.frame_rate is None or abs(info.frame_rate - p.fps) > 0.01:
        problems.append(f"frame rate {info.frame_rate}, expected {p.fps}")
    if info.video_codec != "h264" or info.pixel_format != "yuv420p":
        problems.append(f"video {info.video_codec}/{info.pixel_format}, expected h264/yuv420p")
    if info.audio_codec != "aac" or info.audio_sample_rate != p.audio_sample_rate:
        problems.append(f"audio {info.audio_codec} @ {info.audio_sample_rate}, expected aac @ {p.audio_sample_rate}")
    return problems


def _render_scene(tools: Tools, plan: TimelinePlan, scene: TimelineScene, base: Path, target: Path) -> list[str]:
    work = base / "build" / scene.scene_id
    work.mkdir(parents=True, exist_ok=True)
    for seg in scene.segments:
        if seg.kind == "placeholder":
            ph = Path(seg.path)
            ph.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(ph, placeholder_svg_text(f"{scene.scene_id} · {seg.beat_id}", seg.placeholder_text))
    labels = {}
    for seg in scene.segments:
        if seg.label:
            name = f"label-{seg.beat_id}.txt"
            write_text_atomic(work / name, seg.label)
            labels[seg.beat_id] = name
    captions = None
    if plan.burn_captions and scene.cues:
        write_text_atomic(work / "captions.srt", to_srt([Cue(c.start, c.end, c.text) for c in scene.cues]))
        captions = "captions.srt"

    log = base / "logs" / f"{scene.scene_id}.log"
    _check_decodable(tools, scene, log)
    partial = target.with_name(target.stem + ".partial.mp4")
    cmd = scene_command(tools.ffmpeg, scene, plan.profile, str(partial), label_files=labels, captions_file=captions)
    # Generous but finite: a stuck FFmpeg must never hang the pipeline.
    timeout = max(120.0, scene.duration * SCENE_TIMEOUT_FACTOR)
    _run(cmd, cwd=work, log=log, what=f"scene {scene.scene_id}", timeout=timeout)
    info = probe_video(tools, partial)
    if abs(info.duration_seconds - scene.duration) > SCENE_TOLERANCE or not info.audio_codec:
        raise RenderError(f"scene {scene.scene_id} rendered {info.duration_seconds:.2f} s, expected "
                          f"{scene.duration:.2f} s; kept {partial.name} and {log} for inspection")
    os.replace(partial, target)
    return cmd


def _check_decodable(tools: Tools, scene: TimelineScene, log: Path) -> None:
    """Decode one frame of every picture input first. FFmpeg's looped-image input spins
    forever on an undecodable file, so bad inputs must be caught before the real render."""
    for seg in scene.segments:
        cmd = [tools.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", seg.path, "-frames:v", "1",
               "-f", "null", "-"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
        except subprocess.TimeoutExpired:
            proc = None
        if proc is None or proc.returncode != 0:
            detail = "timed out" if proc is None else proc.stderr.strip()[-300:]
            log.write_text(f"$ {' '.join(cmd)}\n\n{detail}\n", encoding="utf-8")
            raise RenderError(f"scene {scene.scene_id}: {seg.beat_id} input can't be decoded "
                              f"({Path(seg.path).name}); see {log}")


def _concat(tools: Tools, base: Path, files: list[Path], final: Path, plan: TimelinePlan) -> list[str]:
    list_file = base / "build" / "concat.txt"
    write_text_atomic(list_file, concat_list(files))
    partial = final.with_name(final.stem + ".partial.mp4")
    cmd = concat_command(tools.ffmpeg, str(list_file), str(partial))
    _run(cmd, cwd=base / "build", log=base / "logs" / "concat.log", what="concat",
         timeout=max(120.0, plan.total_duration * 2))
    problems = _final_problems(probe_video(tools, partial), plan)
    if problems:
        raise RenderError("final render failed checks: " + "; ".join(problems) + f" (kept {partial.name})")
    os.replace(partial, final)
    return cmd


def _run(cmd: list[str], *, cwd: Path, log: Path, what: str, timeout: float) -> None:
    with log.open("w", encoding="utf-8") as fh:
        fh.write("$ " + " ".join(cmd) + "\n\n")
        fh.flush()
        try:
            proc = subprocess.run(cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RenderError(f"{what}: FFmpeg could not run ({exc}); see {log}") from exc
    if proc.returncode != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:])
        raise RenderError(f"{what}: FFmpeg exited {proc.returncode}; see {log}\n{tail}")


def _write_sidecar(plan: TimelinePlan, path: Path) -> Path | None:
    cues = [Cue(round(s.start + c.start, 3), round(s.start + c.end, 3), c.text) for s in plan.scenes for c in s.cues]
    if not cues:
        return None
    errors, _ = check_cues(cues)
    if errors:
        raise RenderError("final-timeline captions are invalid: " + "; ".join(errors[:3]))
    write_text_atomic(path, to_srt(cues))
    return path


def _record_final_durations(result: ValidationResult, plan: TimelinePlan) -> None:
    durations = {s.scene_id: s.duration for s in plan.scenes}
    scenes = result.scenes.scenes
    if all(s.final_duration_seconds == durations[s.scene_id] for s in scenes):
        return
    updated = []
    for s in scenes:
        # final duration only makes sense once a narrated scene has measured audio
        if s.narration_asset_id is None or s.actual_narration_duration_seconds is not None:
            s = s.model_copy(update={"final_duration_seconds": durations[s.scene_id]})
        updated.append(s)
    write_json_atomic(safe_resolve(result.project_dir, result.manifest.paths.scenes),
                      SceneManifest(scenes=updated).model_dump(mode="json"))


def _write_report(result: ValidationResult, plan: TimelinePlan, started: datetime, status: RenderOutcome,
                  commands: list[list[str]], final: Path | None, info: VideoInfo | None,
                  errors: list[str]) -> Path:
    inputs, seen = [], set()
    for s in plan.scenes:
        if s.narration and s.narration.path not in seen:
            seen.add(s.narration.path)
            inputs.append(RenderInput(path=s.narration.path, sha256=s.narration.sha256, role="narration",
                                      scene_id=s.scene_id))
        for seg in s.segments:
            if seg.sha256 and seg.path not in seen:
                seen.add(seg.path)
                inputs.append(RenderInput(path=seg.path, sha256=seg.sha256, role=f"visual:{seg.kind}",
                                          scene_id=s.scene_id))
    output = None
    if final is not None and info is not None:
        output = RenderOutput(path=str(final), sha256=sha256_file(final), size_bytes=final.stat().st_size,
                              duration_seconds=info.duration_seconds, width=info.width, height=info.height,
                              frame_rate=info.frame_rate, video_codec=info.video_codec, audio_codec=info.audio_codec)
    p = plan.profile
    report = RenderReport(
        project_id=plan.project_id, profile=p.name, status=status, started_at=started.replace(microsecond=0),
        finished_at=datetime.now(timezone.utc).replace(microsecond=0), pipeline_version=__version__,
        ffmpeg_version=plan.ffmpeg_version, commands=commands,
        settings={"width": p.width, "height": p.height, "fps": p.fps, "preset": p.video_preset, "crf": p.crf,
                  "audio_bitrate": p.audio_bitrate, "audio_sample_rate": p.audio_sample_rate,
                  "burn_captions": plan.burn_captions, "placeholders": plan.placeholder_count,
                  "timeline_fingerprint": plan.fingerprint},
        inputs=inputs, output=output, warnings=plan.warnings, errors=errors)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = safe_resolve(result.project_dir, f"reports/render-{p.name}-{stamp}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, report.model_dump(mode="json"))
    return path
