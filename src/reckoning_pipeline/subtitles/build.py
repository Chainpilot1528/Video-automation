"""Build the project's caption file from scenes and the narration report."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..narration.build import REPORT_FILE
from ..project.validate import ValidationResult
from ..schemas import SceneManifest
from ..schemas.narration import NarrationReport
from ..schemas.scene import CaptionStatus
from ..utils.fs import safe_resolve, write_json_atomic, write_text_atomic
from .srt import Cue, ForcedAligner, SceneSpan, aligned_cues, approximate_cues, check_cues, to_srt

CAPTIONS_DIR = "captions"


class CaptionError(RuntimeError):
    """Captions cannot be built yet."""


@dataclass
class CaptionResult:
    path: Path
    cues: list[Cue]
    method: CaptionStatus
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def caption_path(result: ValidationResult) -> str:
    m = result.manifest
    return f"{CAPTIONS_DIR}/{m.project_id}.{m.language}.srt"


def build_captions(result: ValidationResult, *, aligner: ForcedAligner | None = None) -> CaptionResult:
    report_path = safe_resolve(result.project_dir, REPORT_FILE)
    if not report_path.exists():
        raise CaptionError("no narration report; run 'pipeline narration build' first")
    report = NarrationReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    chunks = {c.scene_id: c for c in report.chunks}

    spans, offset, missing = [], 0.0, []
    for scene in sorted(result.scenes.scenes, key=lambda s: s.order):
        chunk = chunks.get(scene.scene_id)
        if not scene.narration_text.strip():
            offset += scene.actual_narration_duration_seconds or 0.0
            continue
        if chunk is None or scene.actual_narration_duration_seconds is None \
                or scene.narration_asset_id != chunk.asset_id \
                or abs(chunk.duration_seconds - scene.actual_narration_duration_seconds) > 0.001:
            missing.append(scene.scene_id)
            continue
        d = chunk.duration_seconds
        start = min(chunk.leading_silence_seconds, d)
        end = max(d - chunk.trailing_silence_seconds, start + 0.01)
        spans.append(SceneSpan(scene.scene_id, scene.narration_text, offset, start, end,
                               safe_resolve(result.project_dir, chunk.path)))
        offset += d
    if missing:
        raise CaptionError(f"narration missing or out of date for: {', '.join(missing)}; "
                           "run 'pipeline narration build'")

    cues: list[Cue] = []
    for span in spans:
        if aligner is not None:
            cues += aligned_cues(span, aligner.align(span.audio_path, span.text))
        else:
            cues += approximate_cues(span)
    method = CaptionStatus.WORD_ALIGNED if aligner is not None else CaptionStatus.APPROXIMATE
    errors, warnings = check_cues(cues)
    out = safe_resolve(result.project_dir, caption_path(result))
    if errors:
        return CaptionResult(out, cues, method, errors, warnings)

    out.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(out, to_srt(cues))
    captioned = {s.scene_id for s in spans}
    scenes = SceneManifest(scenes=[
        s.model_copy(update={"caption_status": method}) if s.scene_id in captioned else s
        for s in result.scenes.scenes])
    write_json_atomic(safe_resolve(result.project_dir, result.manifest.paths.scenes),
                      scenes.model_dump(mode="json"))
    return CaptionResult(out, cues, method, errors, warnings)
