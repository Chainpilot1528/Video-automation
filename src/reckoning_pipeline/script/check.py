"""Script readiness checks and the human script-approval gate."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..approvals import (
    ScriptApprovalState, active_exceptions, append_event, check_reviewer, script_approval_state,
    script_fingerprint,
)
from ..project.validate import ValidationResult
from ..research.report import Finding, build_report
from ..schemas import ApprovalEvent, ApprovalLog
from ..schemas.approval import ApprovalKind
from ..schemas.common import utcnow
from ..schemas.project import ProjectStatus
from ..utils.fs import safe_resolve, write_json_atomic

CLAIM_MARKER_RE = re.compile(r"\[claim:([a-z0-9][a-z0-9_-]{0,63})\]")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
# Structure every script should cover; matched case-insensitively against headings.
REQUIRED_SECTIONS = {
    "cold open": "Cold open / question",
    "stakes": "Stakes and context",
    "investigation": "Investigation",
    "evidence": "Evidence and counter-evidence",
    "resolution": "Resolution or honest uncertainty",
    "source": "Source and visual notes",
}
WORDS_PER_MINUTE = 150
PRE_APPROVAL_STATUSES = (ProjectStatus.DRAFT, ProjectStatus.IN_RESEARCH)


class ScriptError(ValueError):
    """The script cannot be approved (or un-approved) in its current state."""


@dataclass
class ScriptCheck:
    findings: list[Finding] = field(default_factory=list)
    approval: ScriptApprovalState = field(default_factory=lambda: ScriptApprovalState("none"))
    fingerprint: str = ""
    word_count: int = 0

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def estimated_seconds(self) -> float:
        return round(self.word_count / WORDS_PER_MINUTE * 60, 1)


def check_script(result: ValidationResult, log: ApprovalLog) -> ScriptCheck:
    """Assumes ``result`` is a valid project (no errors)."""
    scenes, ledger = result.scenes, result.ledger
    claim_ids = {c.claim_id for c in ledger.claims}
    findings: list[Finding] = []

    script_path = safe_resolve(result.project_dir, result.manifest.paths.script)
    text = script_path.read_text(encoding="utf-8")
    headings = [h.lower() for h in HEADING_RE.findall(text)]
    for key, label in REQUIRED_SECTIONS.items():
        if not any(key in h for h in headings):
            findings.append(Finding("warning", "script.section_missing", result.manifest.paths.script,
                                    f"no '{label}' section heading"))
    for marker in sorted(set(CLAIM_MARKER_RE.findall(text))):
        if marker not in claim_ids:
            findings.append(Finding("blocker", "script.unknown_claim", result.manifest.paths.script,
                                    f"[claim:{marker}] is not in the research ledger", exceptable=False))

    if not scenes.scenes:
        findings.append(Finding("blocker", "script.no_scenes", result.manifest.paths.scenes,
                                "no scenes to approve", exceptable=False))
    for s in scenes.scenes:
        if not s.narration_text.strip():
            findings.append(Finding("warning", "scene.empty_narration", s.scene_id,
                                    "no narration_text (fine for an intentional silent beat)"))

    report = build_report(ledger, scenes, active_exceptions(log, ledger))
    findings = findings + report.findings
    fingerprint = script_fingerprint(scenes, ledger)
    words = sum(len(s.narration_text.split()) for s in scenes.scenes)
    return ScriptCheck(findings, script_approval_state(log, fingerprint), fingerprint, words)


def approve_script(result: ValidationResult, log: ApprovalLog, *, by: str, note: str = "",
                   authorized: list[str] | None = None, at: datetime | None = None) -> ApprovalEvent:
    check_reviewer(by, authorized or [])
    if not result.ok:
        raise ScriptError("project has validation errors; run 'pipeline project validate'")
    check = check_script(result, log)
    if check.blockers:
        raise ScriptError(f"{len(check.blockers)} blocker(s) must be resolved or excepted first; "
                          "run 'pipeline script validate'")
    if check.approval.status == "approved":
        raise ScriptError(f"script is already {check.approval.describe()}")
    event = append_event(result.project_dir, result.manifest, log, kind=ApprovalKind.SCRIPT_APPROVED,
                         by=by, rationale=note, fingerprint=check.fingerprint, at=at)
    if result.manifest.project_status in PRE_APPROVAL_STATUSES:
        _set_status(result, ProjectStatus.SCRIPT_APPROVED)
    return event


def revoke_script_approval(result: ValidationResult, log: ApprovalLog, *, by: str, reason: str,
                           authorized: list[str] | None = None) -> ApprovalEvent:
    check_reviewer(by, authorized or [])
    if not reason.strip():
        raise ScriptError("a reason is required to revoke an approval")
    last = [e for e in log.events
            if e.kind in (ApprovalKind.SCRIPT_APPROVED, ApprovalKind.SCRIPT_APPROVAL_REVOKED)]
    if not last or last[-1].kind is ApprovalKind.SCRIPT_APPROVAL_REVOKED:
        raise ScriptError("there is no script approval to revoke")
    event = append_event(result.project_dir, result.manifest, log,
                         kind=ApprovalKind.SCRIPT_APPROVAL_REVOKED, by=by, rationale=reason)
    if result.manifest.project_status is ProjectStatus.SCRIPT_APPROVED:
        _set_status(result, ProjectStatus.IN_RESEARCH)
    return event


def _set_status(result: ValidationResult, status: ProjectStatus) -> None:
    manifest = result.manifest.model_copy(update={"project_status": status, "updated_at": utcnow()})
    write_json_atomic(Path(result.project_dir) / "project.json", manifest.model_dump(mode="json"))
    result.manifest = manifest
