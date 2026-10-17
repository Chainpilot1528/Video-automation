"""Rights report and credits.

Unknown rights block publication: any asset a scene uses must be approved,
and that approval must still match the asset's current file and rights
fields. These blockers cannot be excepted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..approvals import asset_approval_state
from ..research.report import Finding
from ..schemas import ApprovalLog, AssetRegistry, SceneManifest
from ..schemas.asset import CommercialUse, CreationMethod, PublicationStatus

_ORDER = {"blocker": 0, "warning": 1, "info": 2}
_INHERITED_RIGHTS = ("commercial_use", "license_name", "license_url", "rights_holder", "attribution_text")


def used_asset_ids(scenes: SceneManifest) -> list[str]:
    """Asset IDs used by scenes, in scene order (visuals, then narration)."""
    ordered: list[str] = []
    for s in sorted(scenes.scenes, key=lambda s: s.order):
        for aid in [*s.asset_ids, *([s.narration_asset_id] if s.narration_asset_id else [])]:
            if aid not in ordered:
                ordered.append(aid)
    return ordered


@dataclass
class RightsReport:
    groups: dict[str, list[str]] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    used_asset_ids: list[str] = field(default_factory=list)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    def to_dict(self) -> dict:
        return {"groups": self.groups, "used_asset_ids": self.used_asset_ids,
                "blocker_count": len(self.blockers),
                "findings": [asdict(f) | {"blocking": f.blocking} for f in self.findings]}


def build_rights_report(registry: AssetRegistry, scenes: SceneManifest, log: ApprovalLog) -> RightsReport:
    used = used_asset_ids(scenes)
    assets = {a.asset_id: a for a in registry.assets}
    groups = {s.value: [a.asset_id for a in registry.assets if a.publication_status is s]
              for s in PublicationStatus}
    findings: list[Finding] = []

    def add(severity, code, subject, message):
        findings.append(Finding(severity, code, subject, message, exceptable=False))

    for a in registry.assets:
        in_use = a.asset_id in used
        state = asset_approval_state(log, a)
        if a.publication_status is PublicationStatus.APPROVED:
            if state == "none":
                add("blocker" if in_use else "warning", "asset.approval_unrecorded", a.asset_id,
                    "marked approved but no human review is recorded; run 'pipeline assets review'")
            elif state != "approved":
                add("blocker" if in_use else "warning", "asset.approval_stale", a.asset_id,
                    "file or rights fields changed since it was approved; review it again")
        elif a.publication_status is PublicationStatus.BLOCKED:
            add("blocker" if in_use else "info", "asset.blocked_in_use" if in_use else "asset.blocked",
                a.asset_id, "blocked from publication" + (" but used by a scene" if in_use else ""))
        else:
            gaps = [g for g in a.approval_blockers() if not g.startswith("review_status")]
            detail = f"missing: {'; '.join(gaps)}" if gaps else "rights recorded; ready for human review"
            add("blocker" if in_use else "info", "asset.unapproved_in_use" if in_use else "asset.pending",
                a.asset_id, detail)

        if a.commercial_use is CommercialUse.NOT_ALLOWED and a.publication_status is not PublicationStatus.BLOCKED:
            add("warning", "asset.should_be_blocked", a.asset_id, "commercial use is not allowed")

        parent = assets.get(a.derived_from) if a.derived_from else None
        if parent is not None:
            if parent.derivatives_allowed is False:
                add("blocker" if in_use else "warning", "asset.derivative_not_allowed", a.asset_id,
                    f"parent {parent.asset_id!r} does not allow derivatives")
            differing = [k for k in _INHERITED_RIGHTS if getattr(a, k) != getattr(parent, k)]
            if differing:
                add("warning", "asset.rights_differ_from_parent", a.asset_id,
                    f"rights fields differ from parent {parent.asset_id!r}: {', '.join(differing)}")

    findings.sort(key=lambda f: (_ORDER[f.severity], f.code, f.subject))
    return RightsReport(groups, findings, used)


def format_rights_report(report: RightsReport) -> str:
    lines = [f"{status}: {len(ids)}" + (f" ({', '.join(ids)})" if ids else "")
             for status, ids in report.groups.items()]
    lines += [f"Assets used by scenes: {len(report.used_asset_ids)}", ""]
    lines += [str(f) for f in report.findings] or ["No findings."]
    warnings = sum(f.severity == "warning" for f in report.findings)
    lines += ["", f"{len(report.blockers)} publication blocker(s), {warnings} warning(s)"]
    return "\n".join(lines)


@dataclass
class Credits:
    attributions: list[str] = field(default_factory=list)
    licensed: list[str] = field(default_factory=list)
    generated: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)

    def to_markdown(self, title: str) -> str:
        lines = [f"# Credits: {title}", ""]
        for heading, items in (("Attribution", self.attributions), ("Licensed material", self.licensed),
                               ("AI-generated material", self.generated)):
            if items:
                lines += [f"## {heading}", "", *[f"- {i}" for i in items], ""]
        if len(lines) == 2:
            lines.append("_No third-party or generated material requires credit._")
        return "\n".join(lines).rstrip() + "\n"


def build_credits(registry: AssetRegistry, scenes: SceneManifest) -> Credits:
    """Exact attribution text and licence notes for assets used in scenes."""
    assets = {a.asset_id: a for a in registry.assets}
    credits = Credits()
    for aid in used_asset_ids(scenes):
        a = assets.get(aid)
        if a is None:
            credits.skipped[aid] = "not in registry"
            continue
        if a.publication_status is PublicationStatus.BLOCKED:
            credits.skipped[aid] = "blocked"
            continue
        if a.attribution_required and a.attribution_text and a.attribution_text not in credits.attributions:
            credits.attributions.append(a.attribution_text)
        if a.creation_method in (CreationMethod.DOWNLOADED, CreationMethod.USER_SUPPLIED) and a.license_name:
            line = f"{a.asset_id}: {a.creator or a.rights_holder or 'unknown creator'}, {a.license_name}"
            credits.licensed.append(line + (f" ({a.license_url})" if a.license_url else ""))
        if a.creation_method is CreationMethod.GENERATED and a.generation:
            g = a.generation
            credits.generated.append(f"{a.asset_id}: generated with {g.provider} {g.model}"
                                     + (f" {g.model_version}" if g.model_version else ""))
    return credits
