"""Visuals report: every scene's visual plan, its gaps, and questionable choices.

Placeholders and unresolved beats are reported, never silently filled.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..approvals import asset_approval_state
from ..research.report import Finding
from ..schemas import ApprovalLog, AssetRegistry, ResearchLedger, SceneManifest, VisualPlan
from ..schemas.asset import CreationMethod, PublicationStatus
from ..schemas.research import ClaimType, Importance
from ..schemas.visual import BeatReview, VisualType

_ORDER = {"blocker": 0, "warning": 1, "info": 2}
MAX_TEXT_LINE = 42           # characters, readable on a phone
MAX_TEXT_WORDS = 14          # per on-screen text item
MAX_GENERATED_SHARE = 1 / 3  # prefer a few high-impact generated visuals
PRECISE_TYPES = {ClaimType.STATISTICAL, ClaimType.QUOTATION, ClaimType.HISTORICAL, ClaimType.CAUSAL}
_EXPECTED_METHODS = {
    VisualType.LICENSED_STOCK: {CreationMethod.DOWNLOADED, CreationMethod.USER_SUPPLIED},
    VisualType.GENERATED: {CreationMethod.GENERATED},
    VisualType.ORIGINAL_GRAPHIC: {CreationMethod.ORIGINAL_GRAPHIC},
}


@dataclass
class BeatSummary:
    beat_id: str
    scene_id: str
    order: int
    visual_type: str
    resolved: bool
    rights: str          # approved / pending_review / blocked / stale / missing / -
    review_status: str


@dataclass
class VisualReport:
    findings: list[Finding] = field(default_factory=list)
    beats: list[BeatSummary] = field(default_factory=list)
    type_counts: dict[str, int] = field(default_factory=dict)

    @property
    def gaps(self) -> list[Finding]:
        return [f for f in self.findings if f.code in ("visual.unresolved", "scene.no_visual_plan")]

    def to_dict(self) -> dict:
        return {"type_counts": self.type_counts, "gap_count": len(self.gaps),
                "beats": [asdict(b) for b in self.beats], "findings": [asdict(f) for f in self.findings]}


def build_visual_report(plan: VisualPlan, scenes: SceneManifest, ledger: ResearchLedger,
                        registry: AssetRegistry, log: ApprovalLog) -> VisualReport:
    findings: list[Finding] = []

    def add(severity, code, subject, message):
        findings.append(Finding(severity, code, subject, message, exceptable=False))

    assets = {a.asset_id: a for a in registry.assets}
    claims = {c.claim_id: c for c in ledger.claims}
    by_scene: dict[str, list] = {}
    for b in plan.beats:
        by_scene.setdefault(b.scene_id, []).append(b)

    for s in sorted(scenes.scenes, key=lambda s: s.order):
        beats = sorted(by_scene.get(s.scene_id, []), key=lambda b: b.order)
        if not s.visual_strategy.strip():
            add("warning", "scene.no_visual_strategy", s.scene_id, "scene has no visual_strategy")
        if not beats:
            add("warning", "scene.no_visual_plan", s.scene_id, "no visual beats planned for this scene")
            continue
        precise = [claims[c] for c in s.claim_ids if c in claims
                   and (claims[c].claim_type in PRECISE_TYPES or claims[c].importance is Importance.CRITICAL)]
        strong = [b for b in beats if b.visual_type in (VisualType.PRIMARY_EVIDENCE, VisualType.ORIGINAL_GRAPHIC)]
        if precise and not strong:
            add("warning", "visual.generic_for_precise_claim", s.scene_id,
                f"precise/critical claim(s) {[c.claim_id for c in precise]} are illustrated only by "
                "stock, generated or typographic visuals; prefer evidence or an explanatory graphic")
        if s.asset_ids:
            planned = {a for b in beats for a in b.asset_ids}
            unplanned = [a for a in s.asset_ids if a not in planned]
            if unplanned:
                add("info", "visual.asset_not_in_plan", s.scene_id, f"scene assets not used by any beat: {unplanned}")

    summaries = []
    for b in sorted(plan.beats, key=lambda b: (b.scene_id, b.order)):
        rights = "-"
        if not b.asset_ids:
            add("warning", "visual.unresolved", b.beat_id, f"no asset yet; needs: {b.requirements}")
        else:
            states = []
            for aid in b.asset_ids:
                a = assets.get(aid)
                if a is None:
                    states.append("missing")
                    continue
                state = asset_approval_state(log, a)
                if a.publication_status is PublicationStatus.APPROVED and state != "approved":
                    states.append("stale")
                else:
                    states.append(a.publication_status.value)
                expected = _EXPECTED_METHODS.get(b.visual_type)
                if expected and a.creation_method not in expected:
                    add("warning", "visual.type_mismatch", b.beat_id,
                        f"{b.visual_type} beat uses {aid!r}, a {a.creation_method} asset")
                if a.creation_method is CreationMethod.GENERATED and b.visual_type is not VisualType.GENERATED:
                    add("warning", "visual.unlabelled_generated", b.beat_id,
                        f"{aid!r} is generated but the beat is not marked generated (and so carries no label)")
            rights = min(states, key=["missing", "blocked", "stale", "pending_review", "approved"].index)
            if rights != "approved":
                add("info", "visual.rights_pending", b.beat_id, f"asset rights: {rights}")
        for text in b.on_screen_text:
            if len(text) > MAX_TEXT_LINE or len(text.split()) > MAX_TEXT_WORDS:
                add("warning", "visual.text_too_long", b.beat_id,
                    f"on-screen text {text[:30]!r}… is long for a phone screen "
                    f"(max {MAX_TEXT_LINE} chars / {MAX_TEXT_WORDS} words)")
        if b.review_status is not BeatReview.APPROVED:
            add("info", "visual.review_pending", b.beat_id, f"visual review: {b.review_status}")
        summaries.append(BeatSummary(b.beat_id, b.scene_id, b.order, b.visual_type.value, bool(b.asset_ids),
                                     rights, b.review_status.value))

    counts = {t.value: sum(b.visual_type is t for b in plan.beats) for t in VisualType}
    if plan.beats and counts[VisualType.GENERATED.value] / len(plan.beats) > MAX_GENERATED_SHARE:
        add("warning", "visual.too_many_generated", "plan",
            f"{counts[VisualType.GENERATED.value]} of {len(plan.beats)} beats are generated; "
            "prefer a few high-impact generated visuals")

    findings.sort(key=lambda f: (_ORDER[f.severity], f.code, f.subject))
    return VisualReport(findings, summaries, counts)


def format_visual_report(report: VisualReport) -> str:
    lines = ["Visual types: " + ", ".join(f"{k} {v}" for k, v in report.type_counts.items()), ""]
    for b in report.beats:
        lines.append(f"{b.scene_id:<22} {b.beat_id:<24} {b.visual_type:<17} "
                     f"{'resolved' if b.resolved else 'UNRESOLVED':<10} rights {b.rights:<14} review {b.review_status}")
    lines.append("")
    lines += [str(f) for f in report.findings if f.severity != "info"] or ["No warnings."]
    infos = sum(f.severity == "info" for f in report.findings)
    lines += ["", f"{len(report.gaps)} gap(s), "
                  f"{sum(f.severity == 'warning' for f in report.findings)} warning(s), {infos} info"]
    return "\n".join(lines)
