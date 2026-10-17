"""Research report: what in the claim ledger still needs human attention.

Automated checks produce warnings, not a promise of complete fact-checking.
Blockers only concern claims the narration actually uses; a recorded human
exception (with rationale) can clear an exceptable blocker.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Literal

from ..schemas import ApprovalEvent, ResearchLedger, SceneManifest
from ..schemas.research import (
    CORRELATIONAL_BASES, Claim, ClaimOrigin, ClaimStatus, ClaimType, Importance, SourceStatus,
)

FindingSeverity = Literal["blocker", "warning", "info"]
_ORDER = {"blocker": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    severity: FindingSeverity
    code: str
    subject: str
    message: str
    exceptable: bool = True
    excepted_by: str | None = None

    @property
    def blocking(self) -> bool:
        return self.severity == "blocker" and self.excepted_by is None

    def __str__(self) -> str:
        label = "EXCEPTED" if self.severity == "blocker" and self.excepted_by else self.severity.upper()
        line = f"{label:<8} {self.code:<26} {self.subject}: {self.message}"
        if self.excepted_by:
            line += f" (exception recorded by {self.excepted_by})"
        return line


@dataclass
class ResearchReport:
    findings: list[Finding] = field(default_factory=list)
    status_counts: dict[str, int] = field(default_factory=dict)
    used_claim_ids: list[str] = field(default_factory=list)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    def count(self, severity: FindingSeverity) -> int:
        return sum(f.severity == severity and (severity != "blocker" or f.blocking) for f in self.findings)

    def to_dict(self) -> dict:
        return {
            "status_counts": self.status_counts,
            "used_claim_ids": self.used_claim_ids,
            "blocker_count": len(self.blockers),
            "findings": [asdict(f) | {"blocking": f.blocking} for f in self.findings],
        }


def build_report(ledger: ResearchLedger, scenes: SceneManifest,
                 exceptions: dict[str, ApprovalEvent] | None = None) -> ResearchReport:
    exceptions = exceptions or {}
    sources = {s.source_id: s for s in ledger.sources}
    used_claims = {cid for s in scenes.scenes for cid in s.claim_ids}
    findings: list[Finding] = []

    def add(severity: FindingSeverity, code: str, subject: str, message: str, exceptable: bool = True) -> None:
        excepted = exceptions.get(subject) if severity == "blocker" and exceptable else None
        findings.append(Finding(severity, code, subject, message, exceptable,
                                excepted.by if excepted else None))

    for c in ledger.claims:
        _claim_findings(c, c.claim_id in used_claims, sources, add)

    cited = {sid for c in ledger.claims for sid in c.source_ids} | {
        sid for s in scenes.scenes for sid in s.source_ids}
    for s in ledger.sources:
        if s.source_id not in cited:
            add("warning", "source.unused", s.source_id, "not cited by any claim or scene")

    for s in scenes.scenes:
        if s.narration_text.strip() and not s.claim_ids:
            add("info", "scene.no_claims", s.scene_id,
                "narration lists no claim_ids; confirm it makes no factual claims")

    findings.sort(key=lambda f: (_ORDER[f.severity], f.code, f.subject))
    counts = Counter(c.verification_status.value for c in ledger.claims)
    return ResearchReport(findings, {s.value: counts.get(s.value, 0) for s in ClaimStatus},
                          sorted(used_claims))


def _claim_findings(c: Claim, used: bool, sources: dict, add) -> None:
    cid, status = c.claim_id, c.verification_status
    critical = c.importance is Importance.CRITICAL
    where = "used in narration" if used else "not used in any scene"
    cited = [sources[s] for s in c.source_ids if s in sources]

    if not c.source_ids:
        add("blocker" if used and critical else "warning", "claim.no_sources", cid,
            f"no sources cited ({c.importance}, {where})")

    if status is ClaimStatus.UNVERIFIED:
        if used and critical:
            add("blocker", "claim.critical_unreviewed", cid, "critical claim used in narration is unverified")
        else:
            add("warning" if used else "info", "claim.unverified", cid, f"unverified ({where})")
    elif status is ClaimStatus.PARTIALLY_VERIFIED:
        add("blocker" if used and critical else "warning", "claim.partially_verified", cid,
            f"only partially verified ({where}); state the caveats on screen or in narration")
    elif status is ClaimStatus.DISPUTED:
        add("blocker" if used and critical else "warning", "claim.disputed", cid,
            f"disputed ({where}); narration must present the counter-evidence")
    elif status is ClaimStatus.REJECTED:
        if used:
            add("blocker", "claim.rejected_in_use", cid, "rejected claim is still used in narration",
                exceptable=False)
        else:
            add("info", "claim.rejected", cid, "rejected and unused")

    retracted = [s.source_id for s in cited if s.verification_status is SourceStatus.RETRACTED]
    if retracted:
        add("blocker" if used else "warning", "claim.cites_retracted", cid,
            f"cites retracted source(s) {retracted}", exceptable=False)

    if status is ClaimStatus.VERIFIED:
        supporting = [s for s in cited
                      if s.verification_status is SourceStatus.CHECKED and cid in s.supported_claim_ids]
        if not supporting:
            add("warning", "claim.verified_unsupported", cid,
                "marked verified, but no cited source is both 'checked' and lists this claim")

    if c.claim_type is ClaimType.QUOTATION:
        has_excerpt = any(e.claim_id == cid and e.locator for s in cited for e in s.excerpts)
        if not has_excerpt:
            add("blocker" if used else "warning", "quotation.no_excerpt", cid,
                "quotation has no source excerpt with a page/timestamp locator")

    if c.claim_type is ClaimType.CAUSAL and c.importance in (Importance.CRITICAL, Importance.SUPPORTING):
        if not c.evidence_basis:
            add("warning", "causal.basis_missing", cid, "causal claim does not record its evidence_basis")
        elif set(c.evidence_basis) <= CORRELATIONAL_BASES:
            add("warning", "causal.correlation_only", cid,
                "causal claim rests only on observational/anecdotal/opinion evidence; "
                "consider correlational wording")

    if c.origin is ClaimOrigin.LLM_SUGGESTION and status is ClaimStatus.UNVERIFIED:
        add("info", "claim.ai_suggested", cid, "AI-suggested claim; needs human research and review")


def format_report(report: ResearchReport) -> str:
    counts = ", ".join(f"{k} {v}" for k, v in report.status_counts.items())
    lines = [f"Claims: {counts}", f"Claims used in narration: {len(report.used_claim_ids)}", ""]
    lines += [str(f) for f in report.findings] or ["No findings."]
    excepted = sum(1 for f in report.findings if f.severity == "blocker" and f.excepted_by)
    lines += ["", f"{len(report.blockers)} blocker(s), {report.count('warning')} warning(s), "
                  f"{report.count('info')} info, {excepted} excepted"]
    return "\n".join(lines)
