"""Write QA reports, record waivers and sign-offs.

A sign-off is the human step: a named person confirms they did the review
checklist below and that every blocker is fixed and every warning fixed or
waived. It sets the project to ``publication_ready``. Publishing stays manual.
"""

from __future__ import annotations

from pathlib import Path

from ..approvals import (
    append_event, check_reviewer, qa_inputs_fingerprint, qa_signoff_state, qa_waiver_fingerprint,
)
from ..project.validate import ValidationResult
from ..schemas.approval import MIN_RATIONALE, ApprovalEvent, ApprovalKind
from ..schemas.project import ProjectStatus
from ..schemas.qa import QAReport
from ..script.check import _set_status
from ..utils.fs import sha256_file, write_json_atomic, write_text_atomic
from .checks import qa_paths

SIGNOFF_PROFILE = "master_16x9"

# The human review checklist (build plan, Phase 8). Automated checks can't judge these.
CHECKLIST: dict[str, list[str]] = {
    "Script": [
        "Opens with a compelling question",
        "Has a clear thesis",
        "Every factual claim is supported by its sources",
        "Presents counter-evidence where it exists",
        "States uncertainty honestly",
        "Every section advances the argument",
    ],
    "Visuals": [
        "Each visual communicates the intended idea",
        "No visual implies evidence that doesn't exist",
        "Text and graphics are legible on a phone",
        "Reconstructions and generated images are labelled",
        "Rights and credits are recorded for every visual",
    ],
    "Final video": [
        "The opening is engaging but not misleading",
        "Narration and visuals are in sync",
        "Names, dates, numbers and captions are correct",
        "The voice is clear over the music",
        "No awkward gaps or repetitive visuals",
        "The ending resolves the question or says what remains unknown",
        "Credits and the source list are ready for the description",
    ],
}


class QAError(RuntimeError):
    """A waiver or sign-off can't be recorded."""


def write_report(project_dir: Path, report: QAReport) -> tuple[Path, Path]:
    json_path, md_path = qa_paths(project_dir, report.profile)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(json_path, report.model_dump(mode="json"))
    write_text_atomic(md_path, to_markdown(report))
    return json_path, md_path


def load_report(project_dir: Path, profile: str) -> QAReport | None:
    path, _ = qa_paths(project_dir, profile)
    return QAReport.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def verdict(report: QAReport) -> str:
    if report.blocker_count:
        return "NOT READY"
    if report.open_warning_count:
        return "NEEDS REVIEW"
    if report.profile != SIGNOFF_PROFILE:
        return "CLEAN (preview: sign-off needs a master render)"
    return "READY FOR SIGN-OFF"


def to_markdown(report: QAReport) -> str:
    m = report.measurements
    lines = [
        f"# QA report: {report.project_id} ({report.profile})", "",
        f"**Verdict: {verdict(report)}**: {report.blocker_count} blocker(s), "
        f"{report.open_warning_count} open warning(s).", "",
        f"- Generated: {report.generated_at.isoformat()} (pipeline {report.pipeline_version})",
        f"- Render report: `{report.render_report or 'none'}`",
        f"- Video: `{report.output_path or 'none'}`",
    ]
    if report.media_analysed:
        lines += [
            f"- Duration {m.duration_seconds:.2f} s; loudness {_num(m.integrated_lufs, 'LUFS')}; "
            f"true peak {_num(m.true_peak_dbtp, 'dBTP')}; range {_num(m.loudness_range_lu, 'LU')}",
        ]
    else:
        lines.append("- Media analysis: not run")
    lines.append("")

    blockers = [k for k in report.checks if k.severity == "blocker"]
    warnings = [k for k in report.checks if k.severity == "warning"]
    infos = [k for k in report.checks if k.severity == "info"]
    lines += ["## Blockers (must be fixed)", ""]
    lines += [f"- `{k.code}` **{k.subject}**: {k.message}" for k in blockers] or ["None."]
    lines += ["", "## Warnings (fix, or waive with a written reason)", ""]
    for k in warnings:
        if k.waived_by:
            lines.append(f"- ~~`{k.code}` **{k.subject}**: {k.message}~~ (waived by {k.waived_by}: "
                         f"{k.waiver_rationale})")
        elif k.waivable:
            lines.append(f"- `{k.code}` **{k.subject}**: {k.message}  \n  waive: "
                         f"`pipeline qa waive <project> \"{k.check_id}\" --by NAME --rationale \"...\"`")
        else:
            lines.append(f"- `{k.code}` **{k.subject}**: {k.message} (fix required)")
    if not warnings:
        lines.append("None.")
    if infos:
        lines += ["", "## Notes", "", *[f"- `{k.code}` **{k.subject}**: {k.message}" for k in infos]]

    lines += ["", "## Human review checklist", "",
              "Automated checks can't judge these. Review the video yourself, then sign off.", ""]
    for section, items in CHECKLIST.items():
        lines += [f"**{section}**", "", *[f"- [ ] {i}" for i in items], ""]
    lines += ["## Sign-off", "",
              "When there are no blockers, every warning is fixed or waived, and the checklist is done:", "",
              "```bash",
              f"pipeline qa signoff <project> --by NAME --checklist-done",
              "```", "",
              "Sign-off marks the project `publication_ready`. **Publishing is always manual.**", ""]
    return "\n".join(lines)


def _num(value: float | None, unit: str) -> str:
    return "n/a" if value is None else f"{value:.1f} {unit}"


def waive_warning(result: ValidationResult, report: QAReport, check_id: str, *, by: str, rationale: str,
                  authorized: list[str]) -> ApprovalEvent:
    check_reviewer(by, authorized)
    check = next((k for k in report.checks if k.check_id == check_id), None)
    if check is None:
        raise QAError(f"no check {check_id!r} in the latest {report.profile} QA report")
    if check.severity != "warning":
        raise QAError(f"{check_id} is a {check.severity}; only warnings can be waived. Fix it instead")
    if not check.waivable:
        raise QAError(f"{check_id} can't be waived; fix it instead")
    if check.waived_by:
        raise QAError(f"{check_id} is already waived by {check.waived_by}")
    if len(rationale.strip()) < MIN_RATIONALE:
        raise QAError(f"write a rationale of at least {MIN_RATIONALE} characters explaining why it's acceptable")
    return append_event(result.project_dir, result.manifest, result.approvals, kind=ApprovalKind.QA_WARNING_WAIVED,
                        by=by, rationale=rationale.strip(), qa_check=check_id,
                        fingerprint=qa_waiver_fingerprint(check_id, report.output_sha256))


def sign_off(result: ValidationResult, report: QAReport, *, by: str, checklist_done: bool, note: str,
             authorized: list[str]) -> ApprovalEvent:
    check_reviewer(by, authorized)
    if report.profile != SIGNOFF_PROFILE:
        raise QAError(f"sign-off needs a {SIGNOFF_PROFILE} QA report; previews can't be signed off")
    if not checklist_done:
        raise QAError("confirm you completed the human review checklist with --checklist-done")
    if report.blocker_count or report.open_warning_count:
        raise QAError(f"{report.blocker_count} blocker(s) and {report.open_warning_count} open warning(s) remain; "
                      "fix or waive them and run 'pipeline qa report' again")
    if not report.media_analysed:
        raise QAError("the report skipped media analysis; run 'pipeline qa report' without --skip-media")
    current = qa_inputs_fingerprint(result.manifest, result.scenes, result.ledger, result.registry, result.visuals)
    if report.inputs_fingerprint != current:
        raise QAError("the project changed after this QA report; run 'pipeline qa report' again")
    if report.output_path is None or not Path(report.output_path).is_file() \
            or sha256_file(Path(report.output_path)) != report.output_sha256:
        raise QAError("the rendered video changed or is missing; render and run 'pipeline qa report' again")
    if qa_signoff_state(result.approvals, report.fingerprint) == "current":
        raise QAError("this QA report is already signed off")
    event = append_event(result.project_dir, result.manifest, result.approvals, kind=ApprovalKind.QA_SIGNOFF,
                         by=by, rationale=note.strip() or "Human review checklist completed.",
                         fingerprint=report.fingerprint)
    _set_status(result, ProjectStatus.PUBLICATION_READY)
    return event


def revoke_signoff(result: ValidationResult, *, by: str, reason: str, authorized: list[str]) -> ApprovalEvent:
    check_reviewer(by, authorized)
    if not reason.strip():
        raise QAError("a reason is required to revoke a sign-off")
    last = [e for e in result.approvals.events if e.kind in (ApprovalKind.QA_SIGNOFF, ApprovalKind.QA_SIGNOFF_REVOKED)]
    if not last or last[-1].kind is ApprovalKind.QA_SIGNOFF_REVOKED:
        raise QAError("there is no QA sign-off to revoke")
    event = append_event(result.project_dir, result.manifest, result.approvals,
                         kind=ApprovalKind.QA_SIGNOFF_REVOKED, by=by, rationale=reason.strip())
    if result.manifest.project_status is ProjectStatus.PUBLICATION_READY:
        _set_status(result, ProjectStatus.IN_REVIEW)
    return event
