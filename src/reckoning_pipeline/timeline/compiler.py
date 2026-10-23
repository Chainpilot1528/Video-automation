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
    RenderProfile, TimelineCue, TimelineLayer, TimelineMusic, TimelineNarration, TimelinePlan, TimelineScene,
    TimelineSegment, layers_key,
)
from ..graphics import maps
from ..schemas.visual import ChapterMapView, Motion, VisualBeat
from ..subtitles.srt import SceneSpan, approximate_cues
from ..utils.fs import safe_resolve
from .quotes import word_times

RENDER_VERSION = "2"      # bump when the renderer's output for the same plan changes
DISSOLVE = 0.7            # seconds each shot fades into the next within a scene
ENTER_SECONDS = 0.9       # how long an entrance (rise, settle, slide) takes
RISE = 0.018              # text rises this far (fraction of frame height) as it fades in
SETTLE_FROM = 0.96        # shapes grow from this scale to full size
SLIDE = 0.06              # a sliding element travels this far (fraction of frame width)
IMAGE_PUSH = 1.08         # an image with no motion of its own gets this slow push
MIX_VERSION = "1"         # bump when the music mix changes
# The command builder's source is part of every scene fingerprint, so editing how
# scenes are drawn can never silently reuse renders made by older code.
_RENDER_DIR = Path(__file__).resolve().parent.parent / "render"
RENDERER_DIGEST = hashlib.sha256(b"".join((_RENDER_DIR / name).read_bytes()
                                          for name in ("commands.py", "compose.py"))).hexdigest()
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

        chunk = _current_chunk(chunks.get(scene.scene_id), narration)
        segments = _segments(scene, beats_by_scene.get(scene.scene_id, []), duration, assets, asset_path,
                             placeholder_dir, probe_video, warnings, chunk=chunk, lead=lead)
        cues = _cues(scene, chunks.get(scene.scene_id), narration, lead)
        if narration and scene.narration_text.strip() and not cues:
            warnings.append(f"{scene.scene_id}: no current narration report entry, so no captions for this scene")

        body = {
            "scene_id": scene.scene_id, "duration": duration, "lead_in": lead, "fade_in": fade_in,
            "fade_out": fade_out, "narration": narration.model_dump() if narration else None,
            "segments": [{**s.model_dump(exclude={"path": True, "layers": {"__all__": {"path"}}}),
                          "ref": s.sha256 or s.placeholder_text} for s in segments],
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
              probe_video, warnings, *, chunk=None, lead: float = 0.0) -> list[TimelineSegment]:
    beats = sorted(beats, key=lambda b: b.order)
    items = []  # (beat_id, beat or None, asset or None, placeholder text)
    if beats:
        for b in beats:
            if b.is_composition:
                items.append((b.beat_id, b, None, ""))
                continue
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
        if beat is not None and beat.is_composition:
            layers = _layers(beat, assets, asset_path, warnings)
            if layers is not None and beat.chapter_map is not None:
                below = _map_layers(beat.beat_id, beat.chapter_map, assets, asset_path, warnings)
                layers = None if below is None else below + layers
            if layers is not None:
                layers = [_with_word_times(layer, beat.beat_id, scene, chunk, lead, start, warnings)
                          for layer in layers]
            if layers is None:
                segments.append(TimelineSegment(kind="placeholder", path=str(placeholder_dir / f"{beat_id}.svg"),
                                                sha256=None, placeholder_text=f"Composition {beat_id}: an image "
                                                "layer can't be shown", **common))
                continue
            if beat.chapter_map is None:   # a gentle camera push, so no shot is ever dead still (maps move their own)
                common["motion"] = Motion.SLOW_PUSH
            segments.append(TimelineSegment(kind="composition", path="", sha256=None, layers=layers, **common))
        elif asset is not None and asset.type in IMAGE_TYPES:
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
    return _dissolve(segments, placeholder_dir.parent / scene.scene_id)


def _dissolve(segments: list[TimelineSegment], clip_dir: Path) -> list[TimelineSegment]:
    """Each shot but the last runs DISSOLVE seconds past its end and fades into the next (no dip to black).
    A composition's layers that last to the end of their beat then leave with the dissolve, not before it."""
    out = []
    for i, seg in enumerate(segments):
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        overlap = round(min(DISSOLVE, seg.duration / 3, nxt.duration / 3), 3) if nxt else 0.0
        update: dict = {"overlap": overlap}
        if seg.kind == "composition":
            layers = [_entered(la) for la in seg.layers]
            if overlap:
                layers = [la.model_copy(update={"fade_out": 0.0}) if la.end is None else la for la in layers]
            key = hashlib.sha256((layers_key(layers) + f"|{overlap}").encode()).hexdigest()[:12]
            update |= {"layers": layers, "path": str(clip_dir / f"comp-{seg.beat_id}-{key}.mp4")}
        out.append(seg.model_copy(update=update))
    return out


def _entered(layer: TimelineLayer) -> TimelineLayer:
    """Apply a layer's entrance: text rises into place, shapes settle, images glide (eased) and keep a slow
    push. Only fills in motion the author left unset; explicit drift, zoom or motion windows win."""
    kind = layer.enter
    if kind == "auto":
        kind = {"text": "rise", "shape": "settle"}.get(layer.kind, "none")
    free = layer.motion_start is None and layer.motion_end is None
    up: dict = {}
    window = dict(motion_start=layer.start, motion_end=round(layer.start + ENTER_SECONDS, 3), motion_ease=True)
    if kind == "rise" and free and layer.drift_y == 0 and layer.drift_x == 0:
        up = dict(y=round(layer.y + RISE, 4), drift_y=-RISE, **window)
    elif kind == "settle" and free and layer.zoom_from == layer.zoom_to == 1.0 and layer.shape not in ("stars", "glow"):
        up = dict(zoom_from=SETTLE_FROM, zoom_to=1.0, **window)
    elif kind in ("slide_left", "slide_right") and free and layer.drift_x == 0:
        sign = 1 if kind == "slide_left" else -1        # slide_left: arrives moving left, from the right
        up = dict(x=round(layer.x + sign * SLIDE, 4), drift_x=-sign * SLIDE, **window)
    elif layer.kind == "image" and free:
        if layer.zoom_from == layer.zoom_to == 1.0 and layer.drift_x == layer.drift_y == 0:
            up = dict(zoom_to=IMAGE_PUSH)                # never a dead-still picture
        up["motion_ease"] = True                         # slow moves start and end softly
    return layer.model_copy(update=up) if up else layer


def _layers(beat: VisualBeat, assets, asset_path, warnings) -> list[TimelineLayer] | None:
    """Resolve a composition's image layers to files; None if one can't be shown."""
    out = []
    for layer in beat.layers:
        if layer.kind in ("text", "shape"):
            out.append(TimelineLayer(**layer.model_dump()))
            continue
        asset = assets.get(layer.asset_id)
        if asset is None or asset.type not in IMAGE_TYPES:
            what = "missing" if asset is None else f"a {asset.type}, not an image"
            warnings.append(f"{beat.beat_id}: layer asset {layer.asset_id!r} is {what}; using a placeholder")
            return None
        out.append(TimelineLayer(**layer.model_dump(), path=str(asset_path(asset)), sha256=asset.sha256))
    return out


def _map_layers(beat_id: str, view: ChapterMapView, assets, asset_path, warnings) -> list[TimelineLayer] | None:
    """The chapter map and its medallions as layers sharing one eased camera move; None if it can't be shown."""
    asset = assets.get(view.asset_id)
    info = maps.map_info(Path(asset_path(asset))) if asset is not None and asset.type in IMAGE_TYPES else None
    if info is None:
        warnings.append(f"{beat_id}: {view.asset_id!r} is not a rendered chapter map; using a placeholder")
        return None
    style, n = info
    if max(view.level, view.start_level()) > n:
        warnings.append(f"{beat_id}: the chapter map {view.asset_id!r} has only {n} levels; using a placeholder")
        return None
    fw, fh = 1920, 1080                     # map pixels per frame width / height (maps are drawn for 1920x1080)
    (x0, y0), (x1, y1) = style.view_center(view.start_level(), n), style.view_center(view.level, n)
    pans = (x0, y0) != (x1, y1)
    move = dict(drift_x=round(-(x1 - x0) / fw, 4), drift_y=round(-(y1 - y0) / fh, 4), motion_start=view.pan_start,
                motion_end=view.pan_start + view.pan_seconds, motion_ease=True) if pans else {}
    arrive = view.pan_start + view.pan_seconds if pans else 0.0
    mw, mh = style.map_size(n)
    out = [TimelineLayer(kind="image", asset_id=view.asset_id, path=str(asset_path(asset)), sha256=asset.sha256,
                         x=round(0.5 + (mw / 2 - x0) / fw, 4), y=round(0.5 + (mh / 2 - y0) / fh, 4),
                         width=round(mw / fw, 4), max_height=round(mh / fh + 0.01, 4), fade_in=1.0, fade_out=1.0, **move)]
    if hasattr(style, "core_center"):
        # twinkling stars behind the planet (two fields breathing at different rates), and a glow on the core
        out = [TimelineLayer(kind="shape", shape="stars", width=1.0, max_height=1.0, seed=seed, pulse=period,
                             fade_in=1.0, fade_out=1.0) for seed, period in ((11, 3.7), (23, 5.3))] + out
        gx, gy = style.core_center(n)
        out.append(TimelineLayer(kind="shape", shape="glow", color="accent", x=round(0.5 + (gx - x0) / fw, 4),
                                 y=round(0.5 + (gy - y0) / fh, 4), width=round(style.CORE_GLOW / fw, 4),
                                 max_height=round(style.CORE_GLOW / fh, 4), pulse=4.0, fade_in=1.0, fade_out=1.0,
                                 **move))
    taken: dict[int, set[int]] = {}
    for m in view.markers:
        taken.setdefault(m.level, set()).update({m.slot} if m.slot else set())
    for m in view.markers:
        if m.level > n:
            warnings.append(f"{beat_id}: medallion {m.asset_id!r} is on level {m.level}, below the map; skipped")
            continue
        slot = m.slot or min(set(range(1, style.SLOTS + 1)) - taken[m.level])
        taken[m.level].add(slot)
        a = assets.get(m.asset_id)
        if a is None or a.type not in IMAGE_TYPES:
            warnings.append(f"{beat_id}: medallion asset {m.asset_id!r} is not an image; using a placeholder")
            return None
        ax, ay = style.marker_anchor(m.level, slot, n)
        new = view.level > view.start_level() and m.level == view.level   # arriving downward; a climb is a recap
        timing = dict(start=round(max(arrive - 0.3, 0.0), 3), fade_in=1.2) if new else dict(fade_in=1.0)
        x, y = round(0.5 + (ax - x0) / fw, 4), round(0.5 + (ay - y0) / fh, 4)
        out.append(TimelineLayer(kind="image", asset_id=m.asset_id, path=str(asset_path(a)), sha256=a.sha256,
                                 x=x, y=y, width=round(style.MEDALLION_W / fw, 4),
                                 max_height=round(style.MEDALLION_H / fh, 4), edge="oval", ring=True, crop=m.crop,
                                 fade_out=1.0, **timing, **move))
        if m.name.strip():
            out.append(TimelineLayer(kind="text", text=m.name, text_style="label", x=x,
                                     y=round(y + (style.MEDALLION_H / 2 + 34) / fh, 4), width=0.16,
                                     fade_out=1.0, **timing, **move))
    return out


def _current_chunk(chunk, narration: TimelineNarration | None):
    """The narration report entry, only if it describes the audio this timeline actually uses."""
    if narration is None or chunk is None:
        return None
    if chunk.asset_id != narration.asset_id or abs(chunk.duration_seconds - narration.duration) > 0.001:
        return None
    return chunk


def _with_word_times(layer: TimelineLayer, beat_id: str, scene: Scene, chunk, lead: float, beat_start: float,
                     warnings: list[str]) -> TimelineLayer:
    if layer.kind != "text" or layer.reveal != "words":
        return layer
    times, warning = word_times(layer.text, scene.narration_text, chunk, lead_in=lead, beat_start=beat_start,
                                layer_start=layer.start)
    if warning:
        warnings.append(f"{beat_id}: quote reveal: {warning}")
    return layer.model_copy(update={"word_times": times})


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
