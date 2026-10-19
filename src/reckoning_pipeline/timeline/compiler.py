"""Pure timeline compiler: validated manifests -> TimelinePlan.

No FFmpeg runs here (video durations come from an injected probe), so the
plan can be built, inspected and tested without rendering anything.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from .. import __version__
from ..narration.build import REPORT_FILE
from ..project.validate import ValidationResult
from ..schemas.asset import AssetRoot, AssetType
from ..schemas.narration import NarrationReport
from ..schemas.scene import Scene, TransitionType
from ..schemas.timeline import (
    RenderProfile, TimelineCue, TimelineMusic, TimelineNarration, TimelinePlan, TimelineScene, TimelineSegment,
)
from ..schemas.visual import Motion, VisualBeat
from ..subtitles.srt import SceneSpan, approximate_cues
from ..utils.fs import safe_resolve

RENDER_VERSION = "1"      # bump when the renderer's output for the same plan changes
MIX_VERSION = "1"         # bump when the music mix changes
# The command builder's source is part of every scene fingerprint, so editing how
# scenes are drawn can never silently reuse renders made by older code.
_COMMANDS_SOURCE = Path(__file__).resolve().parent.parent / "render" / "commands.py"
RENDERER_DIGEST = hashlib.sha256(_COMMANDS_SOURCE.read_bytes()).hexdigest()
LEAD_IN = 0.25            # seconds of picture before narration starts
TAIL_HOLD = 0.5           # seconds of picture after narration ends
DEFAULT_SILENT = 3.0      # silent scene with no planned duration
MAX_FADE_SHARE = 1 / 3    # a fade may take at most a third of its scene
RENDERED_MOTION = {Motion.NONE, Motion.SLOW_PUSH, Motion.PAN}
IMAGE_TYPES = {AssetType.IMAGE, AssetType.GRAPHIC}

VideoProbe = Callable[[Path], float]


class TimelineError(ValueError):
    """The project cannot be compiled into a timeline for this profile."""


def _digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _narration_report(result: ValidationResult) -> NarrationReport | None:
    path = safe_resolve(result.project_dir, REPORT_FILE)
    return NarrationReport.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def compile_timeline(result: ValidationResult, profile: RenderProfile, *, ffmpeg_version: str,
                     placeholder_dir: Path, probe_video: VideoProbe | None = None,
                     media_root: Path | None = None, burn_captions: bool = False) -> TimelinePlan:
    if not result.ok:
        raise TimelineError("project has validation errors; run 'pipeline project validate'")
    assets = {a.asset_id: a for a in result.registry.assets}
    beats_by_scene: dict[str, list[VisualBeat]] = {}
    for b in (result.visuals.beats if result.visuals else []):
        beats_by_scene.setdefault(b.scene_id, []).append(b)
    report = _narration_report(result)
    chunks = {c.scene_id: c for c in report.chunks} if report else {}
    errors: list[str] = []
    warnings: list[str] = []

    def asset_path(asset) -> Path:
        if asset.root is AssetRoot.MEDIA:
            if media_root is None:
                raise TimelineError(f"{asset.asset_id} is under the media root but PIPELINE_MEDIA_ROOT is unset")
            return safe_resolve(media_root, asset.path)
        return safe_resolve(result.project_dir, asset.path)

    scenes_out: list[TimelineScene] = []
    clock = 0.0
    dissolve_noted = False
    for scene in sorted(result.scenes.scenes, key=lambda s: s.order):
        narration, duration, lead = _scene_timing(scene, assets, asset_path, profile, errors, warnings)
        fade_in = _fade(scene.transition_in, duration)
        fade_out = _fade(scene.transition_out, duration)
        if not dissolve_noted and TransitionType.DISSOLVE in (scene.transition_in.type, scene.transition_out.type):
            warnings.append("dissolves are rendered as a dip through black of the same length")
            dissolve_noted = True

        segments = _segments(scene, beats_by_scene.get(scene.scene_id, []), duration, assets, asset_path,
                             placeholder_dir, probe_video, warnings)
        cues = _cues(scene, chunks.get(scene.scene_id), narration, lead)
        if narration and scene.narration_text.strip() and not cues:
            warnings.append(f"{scene.scene_id}: no current narration report entry, so no captions for this scene")

        body = {
            "scene_id": scene.scene_id, "duration": duration, "lead_in": lead, "fade_in": fade_in,
            "fade_out": fade_out, "narration": narration.model_dump() if narration else None,
            "segments": [{**s.model_dump(exclude={"path"}), "ref": s.sha256 or s.placeholder_text} for s in segments],
            "cues": [c.model_dump() for c in cues] if burn_captions else [],
            "profile": profile.model_dump(), "burn_captions": burn_captions,
            "render_version": RENDER_VERSION, "renderer": RENDERER_DIGEST, "pipeline_version": __version__,
            "ffmpeg": ffmpeg_version,
        }
        scenes_out.append(TimelineScene(
            scene_id=scene.scene_id, order=scene.order, start=round(clock, 3), duration=duration, lead_in=lead,
            fade_in=fade_in, fade_out=fade_out, narration=narration, segments=segments, cues=cues,
            fingerprint=_digest(body)))
        clock += duration

    music = None
    m = result.manifest.music
    if m is not None:
        bed = assets.get(m.asset_id)
        if bed is None or bed.type is not AssetType.MUSIC:
            errors.append(f"music asset {m.asset_id!r} is missing or not of type music")
        else:
            music = TimelineMusic(asset_id=bed.asset_id, path=str(asset_path(bed)), sha256=bed.sha256,
                                  gain_db=m.gain_db, duck=m.duck, fade_in=m.fade_in_seconds,
                                  fade_out=m.fade_out_seconds)

    placeholders = sum(s.kind == "placeholder" for sc in scenes_out for s in sc.segments)
    if placeholders and not profile.allow_placeholders:
        errors.append(f"{placeholders} placeholder segment(s); the {profile.name} profile needs every visual resolved")
    if errors:
        raise TimelineError("cannot build the timeline:\n- " + "\n- ".join(errors))
    return TimelinePlan(
        project_id=result.manifest.project_id, profile=profile, burn_captions=burn_captions,
        pipeline_version=__version__, ffmpeg_version=ffmpeg_version, total_duration=round(clock, 3),
        scenes=scenes_out, placeholder_count=placeholders, music=music, warnings=warnings,
        fingerprint=_digest([s.fingerprint for s in scenes_out]
                            + ([music.model_dump(exclude={"path"}), MIX_VERSION] if music else [])))


def _scene_timing(scene: Scene, assets, asset_path, profile, errors, warnings):
    """Return (narration, duration, lead_in). Durations come from measured audio, never estimates."""
    narration = None
    if scene.narration_asset_id and scene.actual_narration_duration_seconds is not None:
        a = assets.get(scene.narration_asset_id)
        path = asset_path(a)
        narration = TimelineNarration(asset_id=a.asset_id, path=str(path), sha256=a.sha256,
                                      duration=scene.actual_narration_duration_seconds)
        hold = TAIL_HOLD if scene.hold_after_seconds is None else scene.hold_after_seconds
        return narration, round(LEAD_IN + narration.duration + hold, 3), LEAD_IN

    if scene.narration_text.strip():
        if profile.require_narration:
            errors.append(f"{scene.scene_id}: narration text has no measured audio; run 'pipeline narration build'")
        else:
            warnings.append(f"{scene.scene_id}: no narration audio; silent preview using the planned estimate")
    duration = scene.planned_duration_seconds or DEFAULT_SILENT
    return None, round(duration, 3), 0.0


def _fade(transition, duration: float) -> float:
    if transition.type is TransitionType.CUT:
        return 0.0
    return round(min(transition.duration_seconds, duration * MAX_FADE_SHARE), 3)


def _segments(scene: Scene, beats: list[VisualBeat], duration: float, assets, asset_path, placeholder_dir: Path,
              probe_video, warnings) -> list[TimelineSegment]:
    beats = sorted(beats, key=lambda b: b.order)
    items = []  # (beat_id, beat or None, asset or None, placeholder text)
    if beats:
        for b in beats:
            if len(b.asset_ids) > 1:
                warnings.append(f"{b.beat_id}: only the first of {len(b.asset_ids)} assets is rendered")
            asset = assets.get(b.asset_ids[0]) if b.asset_ids else None
            items.append((b.beat_id, b, asset, "" if asset else f"{b.visual_type.value}: {b.requirements}"))
    else:
        visual = [assets[a] for a in scene.asset_ids
                  if a in assets and assets[a].type in IMAGE_TYPES | {AssetType.VIDEO}]
        if visual:
            items = [(f"{scene.scene_id}-asset-{i}", None, a, "") for i, a in enumerate(visual, 1)]
        else:
            items = [(f"{scene.scene_id}-no-plan", None, None, f"No visual plan for scene {scene.scene_id}")]

    starts = _starts([b for _, b, _, _ in items], duration)
    segments = []
    for i, ((beat_id, beat, asset, ph_text), start) in enumerate(zip(items, starts)):
        end = starts[i + 1] if i + 1 < len(starts) else duration
        seg_duration = round(end - start, 3)
        if seg_duration <= 0:
            warnings.append(f"{beat_id}: no screen time left in {scene.scene_id}; dropped")
            continue
        motion = beat.motion if beat else Motion.NONE
        if motion not in RENDERED_MOTION:
            warnings.append(f"{beat_id}: '{motion}' motion is not rendered automatically yet; shown static")
            motion = Motion.NONE
        label = beat.label if beat and (beat.is_reconstruction or beat.visual_type.value == "generated") else ""
        common = dict(beat_id=beat_id, start=round(start, 3), duration=seg_duration, motion=motion, label=label)
        if asset is not None and asset.type in IMAGE_TYPES:
            segments.append(TimelineSegment(kind="image", path=str(asset_path(asset)), sha256=asset.sha256, **common))
        elif asset is not None and asset.type is AssetType.VIDEO:
            path = asset_path(asset)
            src_d = probe_video(path) if probe_video else None
            segments.append(TimelineSegment(kind="video", path=str(path), sha256=asset.sha256,
                                            source_duration=src_d, **common))
        else:
            if asset is not None:
                warnings.append(f"{beat_id}: {asset.type} assets can't be shown as pictures; using a placeholder")
                ph_text = f"Cannot display {asset.type} asset {asset.asset_id}"
            segments.append(TimelineSegment(kind="placeholder", path=str(placeholder_dir / f"{beat_id}.svg"),
                                            sha256=None, placeholder_text=ph_text, **common))
    return segments


def _starts(beats: list[VisualBeat | None], duration: float) -> list[float]:
    """Segment start times: explicit beat offsets where given, otherwise an even split."""
    n = len(beats)
    if all(b is not None and b.offset_seconds is not None for b in beats) and n:
        starts = [min(b.offset_seconds, duration) for b in beats]
        starts[0] = 0.0  # never open on black: the first visual holds from the scene start
        return sorted(starts)
    return [duration * i / n for i in range(n)]


def _cues(scene: Scene, chunk, narration: TimelineNarration | None, lead: float) -> list[TimelineCue]:
    if narration is None or chunk is None or not scene.narration_text.strip():
        return []
    if chunk.asset_id != narration.asset_id or abs(chunk.duration_seconds - narration.duration) > 0.001:
        return []
    d = chunk.duration_seconds
    start = min(chunk.leading_silence_seconds, d)
    end = max(d - chunk.trailing_silence_seconds, start + 0.01)
    span = SceneSpan(scene.scene_id, scene.narration_text, offset=lead, speech_start=start, speech_end=end)
    return [TimelineCue(start=c.start, end=c.end, text=c.text) for c in approximate_cues(span)]
