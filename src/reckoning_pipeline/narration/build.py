"""Build narration scene by scene, measure it, and record it.

Routes, in order of preference for each scene:

1. **Imported** human narration (``pipeline narration import``): the latest take
   is normalized into a derivative that inherits the take's rights.
2. **TTS**, only when a provider is chosen explicitly.
3. Otherwise the scene is reported as missing narration.

Each output file is named by a fingerprint of its inputs, so a scene is
rebuilt only when its text, take, voice, provider version or audio settings
change, and no existing file is ever overwritten. Durations are always
measured from the audio, never estimated.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .. import __version__
from ..assets.intake import INHERITED_FIELDS, save_registry
from ..media.audio import (
    MediaError, Tools, detect_silence, measure_loudness, normalize_audio, probe_audio,
)
from ..project.validate import ValidationResult
from ..providers.tts import TTSError, TTSOptions, TTSProvider
from ..schemas import Asset, AssetRegistry, SceneManifest
from ..schemas.asset import CommercialUse, CreationMethod, PublicationStatus, ReviewStatus
from ..schemas.common import utcnow
from ..schemas.narration import ChunkReport, NarrationReport, PronunciationList, SentenceTiming
from ..schemas.scene import CaptionStatus, Scene
from .humanize import humanized_tts
from .humanize import settings_key as humanize_settings
from .styles import style_filters
from ..utils.fs import safe_resolve, sha256_file, write_json_atomic

NARRATION_DIR = "narration"
PRONUNCIATIONS_FILE = "narration/pronunciations.json"
REPORT_FILE = "reports/narration.json"
NORMALIZE_VERSION = "1"  # bump when normalize_audio's output changes
_TAKE_RE = re.compile(r"^narr-src-(?P<scene>.+)-t(?P<take>\d+)$")

# Thresholds for chunk checks (warnings, not failures).
MIN_DURATION = 0.3
MAX_LEADING_SILENCE = 1.0
MAX_TRAILING_SILENCE = 1.5
MAX_INTERNAL_GAP = 2.0
TRUE_PEAK_LIMIT = -1.0
WPM_RANGE = (90, 210)
PLANNED_RATIO_RANGE = (0.5, 2.0)
LOUDNESS_SPREAD_LU = 3.0


class NarrationError(RuntimeError):
    """Narration could not be built."""


def narration_asset_id(scene_id: str) -> str:
    return f"narr-{scene_id}"


def take_asset_id(scene_id: str, take: int) -> str:
    return f"narr-src-{scene_id}-t{take}"


def latest_take(registry: AssetRegistry, scene_id: str) -> Asset | None:
    takes = []
    for a in registry.assets:
        m = _TAKE_RE.match(a.asset_id)
        if m and m["scene"] == scene_id:
            takes.append((int(m["take"]), a))
    return max(takes, key=lambda t: t[0])[1] if takes else None


def load_pronunciations(project_dir: Path) -> PronunciationList:
    path = safe_resolve(project_dir, PRONUNCIATIONS_FILE)
    if not path.exists():
        return PronunciationList()
    return PronunciationList.model_validate_json(path.read_text(encoding="utf-8"))


def _scene_speed(options: BuildOptions, scene: Scene) -> float:
    """Project-wide TTS speed times the scene's own pacing multiplier (if any), clamped to 0.5-2.0."""
    return round(min(max(options.speed * (scene.narration_speed or 1.0), 0.5), 2.0), 4)


def _style_key(style: str) -> dict:
    """Style name plus its exact filter chain, so editing a style rebuilds what used it."""
    return {} if style == "none" else {"style": style, "style_filters": style_filters(style)}


def _delivery_key(options: BuildOptions) -> dict:
    """Humanize settings and the delivery instruction. Empty when unused, so older caches stay valid."""
    key: dict = {}
    if options.humanize:
        key["humanize"] = humanize_settings()
    if options.instruct:
        key["instruct"] = options.instruct
    return key


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass
class BuildOptions:
    provider: TTSProvider | None = None
    voice: str | None = None
    rate_wpm: int | None = None
    speed: float = 1.0  # pitch-preserving tempo applied to TTS output (never to human recordings)
    style: str = "none"  # voice processing chain (narration/styles.py), applied to TTS and recordings
    humanize: bool = False  # TTS only: sentence by sentence with natural pauses (narration/humanize.py)
    instruct: str = ""  # TTS only: delivery instruction for engines that take one (Qwen3 CustomVoice)
    scene_ids: list[str] | None = None
    dry_run: bool = False


@dataclass
class PlannedChunk:
    scene: Scene
    route: str  # "imported" | "tts" | "external" | "missing" | "silent"
    fingerprint: str | None = None
    output_rel: str | None = None
    source: Asset | None = None
    tts_text: str | None = None
    speed: float = 1.0  # effective TTS tempo for this scene
    cached: bool = False


@dataclass
class BuildResult:
    report: NarrationReport
    plan: list[PlannedChunk] = field(default_factory=list)


def plan_build(result: ValidationResult, options: BuildOptions) -> list[PlannedChunk]:
    project_dir = result.project_dir
    registry = result.registry
    rate = result.manifest.audio_sample_rate
    pron = load_pronunciations(project_dir)
    assets = {a.asset_id: a for a in registry.assets}
    selected = set(options.scene_ids) if options.scene_ids else None
    if selected and (unknown := selected - {s.scene_id for s in result.scenes.scenes}):
        raise NarrationError(f"unknown scene(s): {sorted(unknown)}")

    plan = []
    for scene in sorted(result.scenes.scenes, key=lambda s: s.order):
        if selected is not None and scene.scene_id not in selected:
            continue
        managed_id = narration_asset_id(scene.scene_id)
        if len(managed_id) > 64:
            raise NarrationError(f"scene_id {scene.scene_id!r} is too long for a narration asset ID")
        take = latest_take(registry, scene.scene_id)
        if take is not None:
            fp = _digest({"route": "imported", "source_sha256": take.sha256, "source_id": take.asset_id,
                          "sample_rate": rate, "normalize": NORMALIZE_VERSION,
                          **_style_key(options.style)})
            chunk = PlannedChunk(scene, "imported", fp, source=take)
        elif options.provider is not None and scene.narration_text.strip():
            if not options.voice:
                raise NarrationError("choose a voice with --voice (see 'pipeline narration voices')")
            text = pron.apply(scene.narration_text)
            fp = _digest({"route": "tts", "provider": options.provider.name,
                          "provider_version": options.provider.version(), "voice": options.voice,
                          "rate_wpm": options.rate_wpm, "speed": _scene_speed(options, scene), "text": text,
                          "sample_rate": rate,
                          "normalize": NORMALIZE_VERSION, **_style_key(options.style), **_delivery_key(options)})
            chunk = PlannedChunk(scene, "tts", fp, tts_text=text, speed=_scene_speed(options, scene))
        elif scene.narration_asset_id and scene.narration_asset_id != managed_id \
                and scene.narration_asset_id in assets:
            plan.append(PlannedChunk(scene, "external", source=assets[scene.narration_asset_id]))
            continue
        else:
            plan.append(PlannedChunk(scene, "missing" if scene.narration_text.strip() else "silent"))
            continue

        chunk.output_rel = f"{NARRATION_DIR}/{scene.scene_id}/{chunk.fingerprint[:16]}.wav"
        existing = assets.get(managed_id)
        out = safe_resolve(project_dir, chunk.output_rel)
        chunk.cached = (existing is not None and existing.path == chunk.output_rel and out.is_file()
                        and sha256_file(out) == existing.sha256)
        plan.append(chunk)
    return plan


def build_narration(result: ValidationResult, tools: Tools, options: BuildOptions) -> BuildResult:
    plan = plan_build(result, options)
    report = NarrationReport(project_id=result.manifest.project_id, built_at=utcnow(),
                             provider=options.provider.name if options.provider else None,
                             voice=options.voice if options.provider else None)
    report.missing = [c.scene.scene_id for c in plan if c.route == "missing"]
    if options.dry_run:
        return BuildResult(report, plan)

    project_dir = result.project_dir
    registry = result.registry
    scenes = {s.scene_id: s for s in result.scenes.scenes}
    rate = result.manifest.audio_sample_rate

    for chunk in plan:
        if chunk.route in ("missing", "silent"):
            continue
        if chunk.route == "external":
            path = safe_resolve(project_dir, chunk.source.path)
            asset = chunk.source
            fingerprint = _digest({"route": "external", "sha256": asset.sha256})
        else:
            path = safe_resolve(project_dir, chunk.output_rel)
            if not chunk.cached:
                _render_chunk(result, tools, options, chunk, path)
            asset = _narration_record(chunk, options, path, rate)
            registry = _upsert(registry, asset)
            fingerprint = chunk.fingerprint

        info = probe_audio(tools, path)
        loud = measure_loudness(tools, path)
        silence = detect_silence(tools, path, info.duration_seconds)
        warnings = _chunk_warnings(chunk.scene, info, loud, silence, rate)
        report.chunks.append(ChunkReport(
            scene_id=chunk.scene.scene_id, asset_id=asset.asset_id,
            route="imported" if chunk.route in ("imported", "external") else "tts",
            path=asset.path, sha256=asset.sha256, fingerprint=fingerprint, cached=chunk.cached,
            duration_seconds=info.duration_seconds, sample_rate=info.sample_rate, channels=info.channels,
            integrated_lufs=loud.integrated_lufs, true_peak_dbtp=loud.true_peak_dbtp,
            leading_silence_seconds=silence.leading_seconds, trailing_silence_seconds=silence.trailing_seconds,
            sentences=_sentences(path), warnings=warnings))
        scenes[chunk.scene.scene_id] = _update_scene(chunk.scene, asset.asset_id, info.duration_seconds)

    report.warnings = _project_warnings(report)
    save_registry(project_dir, result.manifest, registry)
    new_scenes = SceneManifest(scenes=[scenes[s.scene_id] for s in result.scenes.scenes])
    write_json_atomic(safe_resolve(project_dir, result.manifest.paths.scenes), new_scenes.model_dump(mode="json"))
    report_path = safe_resolve(project_dir, REPORT_FILE)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(report_path, report.model_dump(mode="json"))
    return BuildResult(report, plan)


def _render_chunk(result: ValidationResult, tools: Tools, options: BuildOptions, chunk: PlannedChunk,
                  out: Path) -> None:
    rate = result.manifest.audio_sample_rate
    if out.exists():  # left by an interrupted build: same inputs, so reuse rather than overwrite
        return
    try:
        if chunk.route == "imported":
            normalize_audio(tools, safe_resolve(result.project_dir, chunk.source.path), out, sample_rate=rate,
                            extra_filters=style_filters(options.style))
        else:
            tts_options = TTSOptions(rate_wpm=options.rate_wpm,
                                     extra={"instruct": options.instruct} if options.instruct else {})
            with tempfile.TemporaryDirectory() as tmp:
                raw = Path(tmp) / "raw.aiff"
                if options.humanize:
                    timings = humanized_tts(tools, lambda text, path: options.provider.synthesize(
                        text, options.voice, path, tts_options), chunk.tts_text, raw.with_suffix(".wav"),
                        speed=chunk.speed, work_dir=Path(tmp))
                    normalize_audio(tools, raw.with_suffix(".wav"), out, sample_rate=rate,
                                    extra_filters=style_filters(options.style))  # tempo already applied
                    write_json_atomic(timing_path(out), [{"text": t, "start": a, "end": b} for t, a, b in timings])
                else:
                    options.provider.synthesize(chunk.tts_text, options.voice, raw, tts_options)
                    normalize_audio(tools, raw, out, sample_rate=rate, tempo=chunk.speed,
                                    extra_filters=style_filters(options.style))
    except (MediaError, TTSError) as exc:
        raise NarrationError(f"{chunk.scene.scene_id}: {exc}") from exc


def timing_path(audio: Path) -> Path:
    """Sidecar with per-sentence timings, written next to humanized narration."""
    return audio.with_suffix(".timing.json")


def _sentences(path: Path) -> list[SentenceTiming]:
    sidecar = timing_path(path)
    if not sidecar.is_file():
        return []
    try:
        return [SentenceTiming.model_validate(x) for x in json.loads(sidecar.read_text(encoding="utf-8"))]
    except ValueError:
        return []


def _narration_record(chunk: PlannedChunk, options: BuildOptions, path: Path, rate: int) -> Asset:
    scene_id = chunk.scene.scene_id
    base = {"asset_id": narration_asset_id(scene_id), "path": chunk.output_rel, "type": "narration",
            "sha256": sha256_file(path), "intended_scene_ids": [scene_id],
            "review_status": ReviewStatus.PENDING}
    if chunk.route == "imported":
        src = chunk.source
        record = {**{k: getattr(src, k) for k in INHERITED_FIELDS}, **base, "type": "narration",
                  "derived_from": src.asset_id,
                  "publication_status": (PublicationStatus.BLOCKED
                                         if src.commercial_use is CommercialUse.NOT_ALLOWED
                                         else PublicationStatus.PENDING_REVIEW),
                  "notes": f"Normalized from {src.asset_id} to {rate} Hz mono 16-bit WAV."}
    else:
        p = options.provider
        cleared, note, terms = voice_clearance(p, options.voice)
        record = {**base, "creation_method": CreationMethod.GENERATED, "provider": p.name,
                  "rights_holder": "", "creator": p.name,
                  "commercial_use": CommercialUse.ALLOWED if cleared else CommercialUse.NOT_ALLOWED,
                  "attribution_required": False, "derivatives_allowed": True,
                  "rights_evidence": note,
                  "generation": {"provider": p.name, "model": options.voice, "model_version": p.version(),
                                 "generated_on": utcnow().date(), "prompt": chunk.tts_text,
                                 "settings": {"rate_wpm": options.rate_wpm, "speed": chunk.speed,
                                              "style": options.style, "sample_rate": rate,
                                              **({"humanize": True} if options.humanize else {}),
                                              **({"instruct": options.instruct} if options.instruct else {})},
                                 "terms_url": terms},
                  "publication_status": PublicationStatus.PENDING_REVIEW if cleared else PublicationStatus.BLOCKED,
                  "notes": "" if cleared else "Not cleared for publication: " + note}
    return Asset.model_validate(record)


def voice_clearance(provider: TTSProvider, voice: str | None) -> tuple[bool, str, str]:
    """(cleared, note, terms_url) for this provider and voice. Providers whose rights depend on
    the voice (e.g. Voicebox presets vs cloned voices) implement ``voice_clearance``."""
    check = getattr(provider, "voice_clearance", None)
    if check is not None and voice:
        c = check(voice)
        return c.cleared, c.note, c.terms_url
    return provider.commercial_use_cleared, provider.license_note, provider.terms_url


def _upsert(registry: AssetRegistry, asset: Asset) -> AssetRegistry:
    others = [a for a in registry.assets if a.asset_id != asset.asset_id]
    return AssetRegistry(assets=[*others, asset])


def _update_scene(scene: Scene, asset_id: str, duration: float) -> Scene:
    changed = scene.narration_asset_id != asset_id or scene.actual_narration_duration_seconds != duration
    update = {"narration_asset_id": asset_id, "actual_narration_duration_seconds": duration}
    if changed:  # captions and timeline were built for the old audio
        update.update(caption_status=CaptionStatus.NONE, final_duration_seconds=None)
    return scene.model_copy(update=update)


def _chunk_warnings(scene: Scene, info, loud, silence, rate: int) -> list[str]:
    w = []
    d = info.duration_seconds
    if d < MIN_DURATION:
        w.append(f"near-empty audio ({d:.2f} s)")
    if silence.leading_seconds >= d - 0.05:
        w.append("audio is silent")
        return w
    if info.sample_rate != rate:
        w.append(f"sample rate {info.sample_rate} Hz differs from project {rate} Hz")
    if loud.true_peak_dbtp is not None and loud.true_peak_dbtp > TRUE_PEAK_LIMIT:
        w.append(f"true peak {loud.true_peak_dbtp:.1f} dBTP; risk of clipping (keep at or below {TRUE_PEAK_LIMIT} dBTP)")
    if silence.leading_seconds > MAX_LEADING_SILENCE:
        w.append(f"{silence.leading_seconds:.1f} s of leading silence")
    if silence.trailing_seconds > MAX_TRAILING_SILENCE:
        w.append(f"{silence.trailing_seconds:.1f} s of trailing silence")
    for start, length in silence.internal_gaps:
        if length > MAX_INTERNAL_GAP:
            w.append(f"{length:.1f} s pause at {start:.1f} s")
    speech = d - silence.leading_seconds - silence.trailing_seconds
    words = len(scene.narration_text.split())
    if words and speech > 0:
        wpm = words / speech * 60
        if not WPM_RANGE[0] <= wpm <= WPM_RANGE[1]:
            w.append(f"{wpm:.0f} words/min is unusual; check the audio matches the narration text")
    if scene.planned_duration_seconds:
        ratio = d / scene.planned_duration_seconds
        if not PLANNED_RATIO_RANGE[0] <= ratio <= PLANNED_RATIO_RANGE[1]:
            w.append(f"measured {d:.1f} s vs planned estimate {scene.planned_duration_seconds:g} s")
    return w


def _project_warnings(report: NarrationReport) -> list[str]:
    w = [f"{sid}: narration text has no audio yet" for sid in report.missing]
    levels = [c.integrated_lufs for c in report.chunks if c.integrated_lufs is not None]
    if len(levels) > 1 and max(levels) - min(levels) > LOUDNESS_SPREAD_LU:
        w.append(f"narration loudness varies by {max(levels) - min(levels):.1f} LU across scenes "
                 f"({min(levels):.1f} to {max(levels):.1f} LUFS); the mix will need levelling")
    return w
