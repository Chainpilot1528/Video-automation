"""Phase 8 automated QA: technical checks on the latest render plus every publication gate.

Blockers must be fixed; they can't be waived here (claim exceptions and asset
reviews have their own recorded workflows). Warnings must be fixed or waived
by a named person with a written rationale. Nothing here publishes anything.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import __version__
from ..approvals import (
    active_exceptions, qa_inputs_fingerprint, qa_waivers, script_approval_state, script_fingerprint,
)
from ..assets.rights import build_rights_report
from ..media.audio import MediaError, Tools
from ..media.video import probe_video
from ..narration.build import REPORT_FILE
from ..project.validate import STATUS_GATE_CODES, ValidationResult, extra_used_ids
from ..render.profiles import ProfileError, get_profile
from ..render.runner import RENDERS_DIR, _final_problems, ffmpeg_version
from ..research.report import build_report
from ..schemas.narration import NarrationReport
from ..schemas.qa import QACheck, QAMeasurements, QAReport
from ..schemas.render import RenderOutcome, RenderReport
from ..subtitles.srt import check_cues, parse_srt
from ..timeline.compiler import TimelineError, compile_timeline
from ..utils.fs import safe_resolve, sha256_file
from .media import analyse

# Loudness window for a documentary mix (YouTube normalises louder uploads down to about -14 LUFS).
LUFS_RANGE = (-24.0, -13.0)
PEAK_WARN_DBTP = -1.0        # streaming services transcode; keep true peaks under -1 dBTP
PEAK_BLOCK_DBTP = 0.0        # at or over full scale: clipped
NARRATION_SILENT_LUFS = -45.0
NARRATION_PAUSE_SECONDS = 1.5
EDGE_SECONDS = 2.5           # black/silence this close to the start or end is an intended fade

Analyser = Callable[[Tools, Path, float], QAMeasurements]


def _digest(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def qa_paths(project_dir: Path, profile: str) -> tuple[Path, Path]:
    stem = f"reports/qa-{profile}"
    return safe_resolve(project_dir, f"{stem}.json"), safe_resolve(project_dir, f"{stem}.md")


def latest_render_report(project_dir: Path, profile: str) -> tuple[Path, RenderReport] | None:
    """The newest successful render report for this profile (names sort by UTC timestamp)."""
    reports = safe_resolve(project_dir, "reports")
    for path in sorted(reports.glob(f"render-{profile}-*.json"), reverse=True):
        try:
            report = RenderReport.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if report.status is RenderOutcome.SUCCEEDED and report.output is not None:
            return path, report
    return None


class _Checks:
    def __init__(self) -> None:
        self.items: list[QACheck] = []

    def blocker(self, code: str, subject: str, message: str) -> None:
        self.items.append(QACheck(code=code, subject=subject, severity="blocker", message=message, waivable=False))

    def warning(self, code: str, subject: str, message: str, *, waivable: bool = True) -> None:
        self.items.append(QACheck(code=code, subject=subject, severity="warning", message=message, waivable=waivable))

    def info(self, code: str, subject: str, message: str) -> None:
        self.items.append(QACheck(code=code, subject=subject, severity="info", message=message, waivable=False))


def run_qa(result: ValidationResult, tools: Tools, profile_name: str, *, media_root: Path | None = None,
           min_free_gb: float = 0.0, analyse_media: bool = True, analyser: Analyser = analyse) -> QAReport:
    """Run every check and return the report (the caller writes it)."""
    if result.manifest is None:
        raise ValueError("project.json is missing or invalid; run 'pipeline project validate'")
    c = _Checks()
    project_dir = result.project_dir
    _project_checks(c, result)
    usable = result.loaded
    if usable:
        _gate_checks(c, result)
        _narration_checks(c, result)
        _visual_checks(c, result)

    found = latest_render_report(project_dir, profile_name) if usable else None
    output_path = output_sha = render_rel = None
    measurements = QAMeasurements()
    analysed = False
    if usable and found is None:
        c.blocker("render.missing", profile_name,
                  f"no successful {profile_name} render; run 'pipeline render "
                  f"{'master' if profile_name == 'master_16x9' else 'preview'}' first")
    elif found is not None:
        report_path, report = found
        render_rel = f"reports/{report_path.name}"
        output = Path(report.output.path)
        output_path = str(output)
        if _output_checks(c, project_dir, profile_name, output, report):
            output_sha = report.output.sha256
            info = _spec_checks(c, result, tools, profile_name, output, report, media_root)
            _caption_checks(c, output.with_suffix(".srt"), info.duration_seconds if info else None, result)
            if analyse_media and info is not None:
                try:
                    measurements = analyser(tools, output, info.duration_seconds)
                    analysed = True
                    _media_checks(c, measurements)
                except MediaError as exc:
                    c.blocker("media.analysis_failed", "video", f"FFmpeg analysis failed: {exc}")
            elif not analyse_media:
                c.blocker("media.not_analysed", "video",
                          "loudness, peak, silence, black and frozen-frame checks were skipped (--skip-media); "
                          "run the full report before sign-off")
    _disk_check(c, project_dir, min_free_gb)

    waivers = qa_waivers(result.approvals, output_sha) if result.approvals is not None else {}
    checks = []
    for item in c.items:
        w = waivers.get(item.check_id)
        if item.severity == "warning" and item.waivable and w is not None:
            item = item.model_copy(update={"waived_by": w.by, "waiver_rationale": w.rationale})
        checks.append(item)
    order = {"blocker": 0, "warning": 1, "info": 2}
    checks.sort(key=lambda k: (order[k.severity], k.code, k.subject))

    inputs = (qa_inputs_fingerprint(result.manifest, result.scenes, result.ledger, result.registry, result.visuals)
              if usable else _digest(["invalid", str(project_dir)]))
    blockers = sum(k.severity == "blocker" for k in checks)
    open_warnings = sum(k.severity == "warning" and k.open for k in checks)
    fingerprint = _digest({
        "profile": profile_name, "output": output_sha, "inputs": inputs, "analysed": analysed,
        "checks": [(k.check_id, k.severity, k.waived_by) for k in checks],
    })
    return QAReport(
        project_id=result.manifest.project_id, profile=profile_name,
        generated_at=datetime.now(timezone.utc).replace(microsecond=0), pipeline_version=__version__,
        render_report=render_rel, output_path=output_path, output_sha256=output_sha, inputs_fingerprint=inputs,
        media_analysed=analysed, measurements=measurements, checks=checks, blocker_count=blockers,
        open_warning_count=open_warnings, fingerprint=fingerprint)


# --- project and publication gates ----------------------------------------------

def _project_checks(c: _Checks, result: ValidationResult) -> None:
    for issue in result.errors:
        if issue.code not in STATUS_GATE_CODES:  # QA re-checks those gates itself
            c.blocker(f"project.{issue.code}", issue.location, issue.message)
    for issue in result.warnings:
        c.warning(f"project.{issue.code}", issue.location, issue.message)


def _gate_checks(c: _Checks, result: ValidationResult) -> None:
    state = script_approval_state(result.approvals, script_fingerprint(result.scenes, result.ledger))
    if state.status != "approved":
        c.blocker("script.not_approved", "script", f"script is {state.describe()}; run 'pipeline script approve'")

    research = build_report(result.ledger, result.scenes, active_exceptions(result.approvals, result.ledger))
    for f in research.findings:
        if f.blocking:
            c.blocker(f"research.{f.code}", f.subject, f.message)

    rights = build_rights_report(result.registry, result.scenes, result.approvals,
                                 extra_used_ids(result.manifest, result.visuals))
    for f in rights.findings:
        if f.blocking:
            c.blocker(f"rights.{f.code}", f.subject, f.message)
        elif f.severity == "warning":
            c.warning(f"rights.{f.code}", f.subject, f.message)

    assets = {a.asset_id: a for a in result.registry.assets}
    for aid in rights.used_asset_ids:
        a = assets.get(aid)
        if a is not None and a.attribution_required and not (a.attribution_text or "").strip():
            c.blocker("credits.attribution_missing", aid, "the licence requires attribution, but no attribution "
                                                          "text is recorded")


def _narration_checks(c: _Checks, result: ValidationResult) -> None:
    path = safe_resolve(result.project_dir, REPORT_FILE)
    report = NarrationReport.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None
    chunks = {ch.scene_id: ch for ch in report.chunks} if report else {}
    assets = {a.asset_id: a for a in result.registry.assets}
    for s in sorted(result.scenes.scenes, key=lambda s: s.order):
        if not s.narration_text.strip():
            continue
        if s.narration_asset_id is None or s.actual_narration_duration_seconds is None:
            c.blocker("narration.missing", s.scene_id, "narration text has no measured audio; "
                                                     "run 'pipeline narration build'")
            continue
        ch = chunks.get(s.scene_id)
        asset = assets.get(s.narration_asset_id)
        if ch is None or asset is None or ch.sha256 != asset.sha256:
            c.warning("narration.unmeasured", s.scene_id, "the narration report doesn't match the current audio; "
                                                         "re-run 'pipeline narration build' to re-measure it")
            continue
        if ch.integrated_lufs is None or ch.integrated_lufs < NARRATION_SILENT_LUFS:
            c.blocker("narration.silent", s.scene_id,
                      f"narration is silent or nearly silent ({ch.integrated_lufs} LUFS)")
        if ch.true_peak_dbtp is not None:
            if ch.true_peak_dbtp >= PEAK_BLOCK_DBTP:
                c.blocker("narration.clipped", s.scene_id, f"true peak {ch.true_peak_dbtp:+.1f} dBTP: clipped")
            elif ch.true_peak_dbtp > PEAK_WARN_DBTP:
                c.warning("narration.peak_high", s.scene_id, f"true peak {ch.true_peak_dbtp:+.1f} dBTP "
                                                             f"(keep under {PEAK_WARN_DBTP:g})")
        for where, secs in (("leading", ch.leading_silence_seconds), ("trailing", ch.trailing_silence_seconds)):
            if secs > NARRATION_PAUSE_SECONDS:
                c.warning("narration.long_pause", f"{s.scene_id}:{where}", f"{secs:.1f} s of {where} silence")


def _visual_checks(c: _Checks, result: ValidationResult) -> None:
    beats = result.visuals.beats if result.visuals else []
    counts = Counter(b.asset_ids[0] for b in beats if b.asset_ids)
    for aid, n in sorted(counts.items()):
        if n > 1:
            c.warning("visual.repeated", aid, f"the same visual is used in {n} beats")


# --- the render ------------------------------------------------------------------

def _output_checks(c: _Checks, project_dir: Path, profile: str, output: Path, report: RenderReport) -> bool:
    """Existence, size, checksum and location. Returns True if the file can be inspected further."""
    approved_dir = safe_resolve(project_dir, f"{RENDERS_DIR}/{profile}")
    try:
        output.resolve().relative_to(approved_dir.resolve())
    except ValueError:
        c.blocker("output.path_unapproved", str(output), f"renders must live under {approved_dir}")
        return False
    if not output.is_file():
        c.blocker("output.missing", output.name, "the rendered file no longer exists; render again")
        return False
    if output.stat().st_size == 0:
        c.blocker("output.empty", output.name, "the rendered file is empty")
        return False
    if sha256_file(output) != report.output.sha256:
        c.blocker("output.changed", output.name, "the file no longer matches its render report; render again")
        return False
    return True


def _spec_checks(c: _Checks, result: ValidationResult, tools: Tools, profile_name: str, output: Path,
                 report: RenderReport, media_root: Path | None):
    try:
        info = probe_video(tools, output)
    except MediaError as exc:
        c.blocker("output.unreadable", output.name, str(exc))
        return None
    try:
        profile = get_profile(profile_name, result.manifest)
    except ProfileError as exc:
        c.blocker("output.profile", profile_name, str(exc))
        return info
    base = safe_resolve(result.project_dir, f"{RENDERS_DIR}/{profile.name}")
    try:
        gateless = replace(result, issues=[i for i in result.issues if i.code not in STATUS_GATE_CODES])
        plan = compile_timeline(gateless, profile, ffmpeg_version=ffmpeg_version(tools),
                                placeholder_dir=base / "build" / "placeholders",
                                probe_video=lambda p: probe_video(tools, p).duration_seconds,
                                media_root=media_root)
    except TimelineError as exc:
        c.blocker("timeline.invalid", profile_name, str(exc))
        return info
    for problem in _final_problems(info, plan):
        c.blocker("output.spec", output.name, problem)
    if report.settings.get("timeline_fingerprint") != plan.fingerprint:
        c.blocker("render.stale", output.name, "the project changed since this render; render again")
    else:
        for s in plan.scenes:
            if not (base / "scenes" / f"{s.scene_id}-{s.fingerprint[:16]}.mp4").is_file():
                c.warning("scene.render_missing", s.scene_id, "the cached scene render is gone (the final video "
                                                              "is intact; re-rendering will rebuild it)")
    if plan.placeholder_count:
        c.blocker("visual.placeholders", output.name, f"{plan.placeholder_count} placeholder frame(s) in the video")
    for w in plan.warnings:
        c.warning("timeline.warning", _subject_of(w), w)
    return info


def _subject_of(message: str) -> str:
    """A stable subject for a timeline warning, so a waiver keeps matching the same warning."""
    head = message.split(":", 1)[0]
    if head and " " not in head:
        return head
    return "timeline-" + hashlib.sha256(message.encode("utf-8")).hexdigest()[:8]


def _caption_checks(c: _Checks, srt: Path, duration: float | None, result: ValidationResult) -> None:
    narrated = any(s.narration_text.strip() for s in result.scenes.scenes) if result.scenes else False
    if not srt.is_file():
        if narrated:
            c.warning("captions.missing", srt.name, "no caption file next to the video")
        return
    try:
        cues = parse_srt(srt.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        c.blocker("captions.invalid", srt.name, f"can't be parsed: {exc}")
        return
    errors, warnings = check_cues(cues)
    for e in errors:
        c.blocker("captions.invalid", srt.name, e)
    if warnings:
        shown = "; ".join(warnings[:3]) + (f"; and {len(warnings) - 3} more" if len(warnings) > 3 else "")
        c.warning("captions.readability", srt.name, f"{len(warnings)} readability note(s): {shown}")
    if cues and duration is not None and cues[-1].end > duration + 0.05:
        c.blocker("captions.past_end", srt.name, f"last caption ends at {cues[-1].end:.2f} s, after the video "
                                                 f"({duration:.2f} s)")


def _media_checks(c: _Checks, m: QAMeasurements) -> None:
    d = m.duration_seconds or 0.0
    if m.integrated_lufs is None or m.integrated_lufs < -60:
        c.blocker("audio.silent", "video", "the soundtrack is silent")
    else:
        lo, hi = LUFS_RANGE
        if not lo <= m.integrated_lufs <= hi:
            c.warning("audio.loudness", "video", f"{m.integrated_lufs:.1f} LUFS integrated; expected {lo:g} to {hi:g}")
    if m.true_peak_dbtp is not None:
        if m.true_peak_dbtp >= PEAK_BLOCK_DBTP:
            c.blocker("audio.clipped", "video", f"true peak {m.true_peak_dbtp:+.1f} dBTP: the mix clips")
        elif m.true_peak_dbtp > PEAK_WARN_DBTP:
            c.warning("audio.peak_high", "video", f"true peak {m.true_peak_dbtp:+.1f} dBTP (keep under "
                                                  f"{PEAK_WARN_DBTP:g})")

    def inner(start: float, length: float) -> bool:
        return start > EDGE_SECONDS and start + length < d - EDGE_SECONDS

    for start, length in m.silent_intervals:
        if inner(start, length):
            c.warning("audio.long_silence", f"{start:.1f}s", f"{length:.1f} s of silence")
    for start, length in m.black_intervals:
        if inner(start, length):
            c.warning("picture.black", f"{start:.1f}s", f"{length:.1f} s of near-black picture (may be a deliberate "
                                                       "dark shot or fade)")
    for start, length in m.frozen_intervals:
        c.warning("picture.frozen", f"{start:.1f}s", f"{length:.1f} s with no visible change (may be a deliberate "
                                                    "still shot)")


def _disk_check(c: _Checks, project_dir: Path, min_free_gb: float) -> None:
    free = shutil.disk_usage(project_dir).free / 1024**3
    if free < min_free_gb:
        c.warning("disk.low", str(project_dir), f"{free:.1f} GiB free, below the {min_free_gb:g} GiB margin")
