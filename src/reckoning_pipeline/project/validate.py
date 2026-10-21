"""Whole-project validation: files, schemas, references, paths and checksums.

Problems are collected as issues rather than raised, so one run reports
everything that needs fixing. Errors make a project invalid; warnings do not.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ValidationError

from ..assets.rights import build_rights_report
from ..approvals import (
    active_exceptions, qa_inputs_fingerprint, qa_signoff_state, script_approval_state, script_fingerprint,
)
from ..research.report import build_report
from ..schemas import ApprovalLog, AssetRegistry, ProjectManifest, ResearchLedger, SceneManifest, VisualPlan
from ..schemas.project import ProjectStatus
from ..schemas.qa import QAReport
from ..schemas.asset import AssetRoot, AssetType
from ..schemas.common import SUPPORTED_SCHEMA_VERSIONS, duplicates
from ..utils.fs import UnsafePathError, safe_resolve, sha256_file
from .scaffold import MANIFEST_NAME

Severity = Literal["error", "warning"]
M = TypeVar("M", bound=BaseModel)
NARRATION_TYPES = {AssetType.NARRATION, AssetType.AUDIO}
APPROVAL_REQUIRED = {ProjectStatus.SCRIPT_APPROVED, ProjectStatus.IN_PRODUCTION,
                     ProjectStatus.IN_REVIEW, ProjectStatus.PUBLICATION_READY}
_ID_KEYS = ("scene_id", "source_id", "claim_id", "asset_id")
# Errors raised only because project_status claims more than the approvals support. QA, sign-off
# and revoke exist to resolve these, so they must still run while these errors are present.
STATUS_GATE_CODES = frozenset({"project.qa_signoff_required", "project.publication_blocked",
                               "project.status_requires_approval"})


@dataclass(frozen=True)
class Issue:
    severity: Severity
    code: str
    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():<7} {self.code:<22} {self.location}: {self.message}"


@dataclass
class ValidationResult:
    project_dir: Path
    manifest: ProjectManifest | None = None
    ledger: ResearchLedger | None = None
    scenes: SceneManifest | None = None
    registry: AssetRegistry | None = None
    approvals: ApprovalLog | None = None
    visuals: VisualPlan | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def loaded(self) -> bool:
        """Every file loaded and no errors except status-gate ones."""
        return None not in (self.manifest, self.scenes, self.ledger, self.registry, self.approvals) and all(
            i.code in STATUS_GATE_CODES for i in self.errors)

    def add(self, severity: Severity, code: str, location: str, message: str) -> None:
        self.issues.append(Issue(severity, code, location, message))


def validate_project(path: Path, *, media_root: Path | None = None,
                     verify_checksums: bool = True) -> ValidationResult:
    result = ValidationResult(project_dir=path)
    if not path.exists():
        result.add("error", "path.missing", str(path), "does not exist")
        return result
    if not path.is_dir():
        result.add("error", "path.not_directory", str(path), "pass the project folder, not a file")
        return result

    result.manifest = _load(result, path, MANIFEST_NAME, ProjectManifest)
    if result.manifest is None:
        return result
    manifest = result.manifest
    folder = path.resolve().name
    if manifest.project_id != folder:
        result.add("warning", "project.id_mismatch", MANIFEST_NAME,
                   f"project_id {manifest.project_id!r} differs from folder name {folder!r}")

    for label in ("brief", "script"):
        _resolve_existing(result, path, getattr(manifest.paths, label), f"paths.{label}")
    result.ledger = _load(result, path, manifest.paths.research_ledger, ResearchLedger)
    result.scenes = _load(result, path, manifest.paths.scenes, SceneManifest)
    result.registry = _load(result, path, manifest.paths.asset_registry, AssetRegistry)
    result.approvals = _load_optional(result, path, manifest.paths.approvals, ApprovalLog)
    result.visuals = _load_optional(result, path, manifest.paths.visual_plan, VisualPlan)

    _check_ids(result)
    _check_references(result)
    _check_approvals(result)
    _check_visuals(result)
    _check_music(result)
    if result.registry is not None:
        _check_asset_files(result, path, media_root, verify_checksums)
    _check_status_gates(result)
    return result


# --- loading -----------------------------------------------------------------

def _resolve_existing(result: ValidationResult, root: Path, rel: str, location: str) -> Path | None:
    try:
        target = safe_resolve(root, rel)
    except UnsafePathError as exc:
        result.add("error", "path.unsafe", location, str(exc))
        return None
    if not target.is_file():
        result.add("error", "file.missing", location, f"{rel} not found")
        return None
    return target


def _load(result: ValidationResult, root: Path, rel: str, model: type[M]) -> M | None:
    target = _resolve_existing(result, root, rel, rel)
    if target is None:
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.add("error", "json.invalid", rel, f"line {exc.lineno}, column {exc.colno}: {exc.msg}")
        return None
    except UnicodeDecodeError:
        result.add("error", "json.invalid", rel, "file is not UTF-8 text")
        return None
    if not isinstance(data, dict):
        result.add("error", "json.invalid", rel, "top level must be a JSON object")
        return None
    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        hint = " Run 'pipeline project migrate <path>'." if version == "0.1" else ""
        result.add("error", "schema.unsupported_version", rel,
                   f"schema_version {version!r} is not supported "
                   f"(supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}).{hint}")
        return None
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            result.add("error", "schema.invalid", f"{rel}: {_describe_loc(data, err['loc'])}",
                       _clean_msg(err["msg"]))
        return None


def _load_optional(result: ValidationResult, root: Path, rel: str, model: type[M]) -> M | None:
    """Like _load, but a missing file means "empty" rather than an error."""
    try:
        exists = safe_resolve(root, rel).exists()
    except UnsafePathError as exc:
        result.add("error", "path.unsafe", rel, str(exc))
        return None
    return _load(result, root, rel, model) if exists else model()


def _describe_loc(data: Any, loc: tuple) -> str:
    """Render a pydantic error location, tagging list items with their record ID."""
    parts, node = [], data
    for key in loc:
        if isinstance(key, int):
            label = f"[{key}]"
            if isinstance(node, list) and key < len(node) and isinstance(node[key], dict):
                record_id = next((node[key][k] for k in _ID_KEYS if k in node[key]), None)
                if record_id is not None:
                    label = f"[{key}]({record_id})"
            parts.append(label)
        else:
            parts.append(("." if parts else "") + str(key))
        try:
            node = node[key]
        except (KeyError, IndexError, TypeError):
            node = None
    return "".join(parts) or "(root)"


def _clean_msg(msg: str) -> str:
    return msg.removeprefix("Value error, ")


# --- cross-file checks -------------------------------------------------------

def _check_ids(result: ValidationResult) -> None:
    def dupes(values: list, code: str, location: str, what: str) -> None:
        for value in duplicates(values):
            result.add("error", code, location, f"duplicate {what} {value!r}")

    if result.scenes:
        rel = result.manifest.paths.scenes
        dupes([s.scene_id for s in result.scenes.scenes], "id.duplicate", rel, "scene_id")
        dupes([s.order for s in result.scenes.scenes], "scene.order_duplicate", rel, "order")
    if result.ledger:
        rel = result.manifest.paths.research_ledger
        dupes([s.source_id for s in result.ledger.sources], "id.duplicate", rel, "source_id")
        dupes([c.claim_id for c in result.ledger.claims], "id.duplicate", rel, "claim_id")
    if result.registry:
        rel = result.manifest.paths.asset_registry
        dupes([a.asset_id for a in result.registry.assets], "id.duplicate", rel, "asset_id")
        locations = Counter((a.root, a.path) for a in result.registry.assets)
        for (root, p), n in locations.items():
            if n > 1:
                result.add("error", "asset.path_duplicate", rel,
                           f"{n} assets share path {p!r} (root {root}); each file needs one record")


def _check_references(result: ValidationResult) -> None:
    paths = result.manifest.paths
    scenes = result.scenes.scenes if result.scenes else []
    sources = {s.source_id: s for s in result.ledger.sources} if result.ledger else None
    claims = {c.claim_id: c for c in result.ledger.claims} if result.ledger else None
    assets = {a.asset_id: a for a in result.registry.assets} if result.registry else None
    scene_ids = {s.scene_id for s in scenes} if result.scenes else None

    def missing(ref: str, pool: dict | set | None, code: str, location: str, what: str) -> None:
        if pool is not None and ref not in pool:
            result.add("error", code, location, f"unknown {what} {ref!r}")

    for s in scenes:
        loc = f"{paths.scenes}: {s.scene_id}"
        for a in s.asset_ids:
            missing(a, assets, "ref.missing_asset", loc, "asset_id")
        for src in s.source_ids:
            missing(src, sources, "ref.missing_source", loc, "source_id")
        for c in s.claim_ids:
            missing(c, claims, "ref.missing_claim", loc, "claim_id")
        if s.narration_asset_id is not None:
            missing(s.narration_asset_id, assets, "ref.missing_asset", loc, "narration_asset_id")
            narration = (assets or {}).get(s.narration_asset_id)
            if narration is not None and narration.type not in NARRATION_TYPES:
                result.add("error", "ref.wrong_asset_type", loc,
                           f"narration_asset_id {s.narration_asset_id!r} is a {narration.type}, "
                           "not narration/audio")

    if result.ledger:
        rel = paths.research_ledger
        for c in result.ledger.claims:
            for src in c.source_ids:
                missing(src, sources, "ref.missing_source", f"{rel}: {c.claim_id}", "source_id")
                if src in sources and c.claim_id not in sources[src].supported_claim_ids:
                    result.add("warning", "ledger.asymmetric", f"{rel}: {c.claim_id}",
                               f"claim cites {src!r}, but that source does not list this claim "
                               "in supported_claim_ids")
        for s in result.ledger.sources:
            for c in s.supported_claim_ids:
                missing(c, claims, "ref.missing_claim", f"{rel}: {s.source_id}", "claim_id")
                if c in claims and s.source_id not in claims[c].source_ids:
                    result.add("warning", "ledger.asymmetric", f"{rel}: {s.source_id}",
                               f"source lists claim {c!r}, but that claim does not cite this source")

    if result.registry:
        rel = paths.asset_registry
        used = {a for s in scenes for a in s.asset_ids} | {
            s.narration_asset_id for s in scenes if s.narration_asset_id} | set(music_ids(result.manifest))
        for a in result.registry.assets:
            loc = f"{rel}: {a.asset_id}"
            for sid in a.intended_scene_ids:
                missing(sid, scene_ids, "ref.missing_scene", loc, "scene_id")
            if a.derived_from is not None:
                missing(a.derived_from, assets, "ref.missing_asset", loc, "derived_from")
                parent = assets.get(a.derived_from)
                if parent is not None and parent.derivatives_allowed is False:
                    result.add("error", "asset.derivative_not_allowed", loc,
                               f"derived from {a.derived_from!r}, which does not allow derivatives")
                if a.path.startswith("assets/originals/"):
                    result.add("warning", "asset.derived_in_originals", loc,
                               "derivatives belong in assets/derived/, keeping originals untouched")
            if result.scenes and a.asset_id not in used and not a.intended_scene_ids \
                    and a.asset_id not in {x.derived_from for x in result.registry.assets}:
                result.add("warning", "asset.unused", loc, "not used by any scene")


def _check_approvals(result: ValidationResult) -> None:
    if result.approvals is None:
        return
    rel = result.manifest.paths.approvals
    events = result.approvals.events
    for value in duplicates([e.event_id for e in events]):
        result.add("error", "id.duplicate", rel, f"duplicate event_id {value!r}")
    for prev, cur in zip(events, events[1:]):
        if cur.at < prev.at:
            result.add("error", "approvals.out_of_order", rel,
                       f"{cur.event_id} is dated before {prev.event_id}; the log is append-only")
    if result.ledger is not None:
        claim_ids = {c.claim_id for c in result.ledger.claims}
        for e in events:
            if e.claim_id is not None and e.claim_id not in claim_ids:
                result.add("warning", "approvals.unknown_claim", f"{rel}: {e.event_id}",
                           f"refers to claim {e.claim_id!r}, which is no longer in the ledger")


def music_ids(manifest: ProjectManifest) -> tuple[str, ...]:
    return (manifest.music.asset_id,) if manifest.music else ()


def extra_used_ids(manifest: ProjectManifest, visuals: VisualPlan | None) -> tuple[str, ...]:
    """Assets that reach the video outside scenes' asset_ids: the music bed and visual-plan beats.
    A plain beat renders only its first asset; a composition renders every layer's image."""
    ids = list(music_ids(manifest))
    for b in sorted(visuals.beats if visuals else [], key=lambda b: (b.scene_id, b.order)):
        shown = b.asset_ids if b.layers else b.asset_ids[:1]
        ids += [a for a in shown if a not in ids]
    return tuple(ids)


def _check_music(result: ValidationResult) -> None:
    m = result.manifest.music
    if m is None or result.registry is None:
        return
    asset = next((a for a in result.registry.assets if a.asset_id == m.asset_id), None)
    if asset is None:
        result.add("error", "ref.missing_asset", f"{MANIFEST_NAME}: music", f"unknown asset {m.asset_id!r}")
    elif asset.type is not AssetType.MUSIC:
        result.add("error", "music.wrong_type", f"{MANIFEST_NAME}: music", f"{m.asset_id!r} is a {asset.type}, not music")


def _check_visuals(result: ValidationResult) -> None:
    if not result.visuals:
        return
    rel = result.manifest.paths.visual_plan
    beats = result.visuals.beats
    for value in duplicates([b.beat_id for b in beats]):
        result.add("error", "id.duplicate", rel, f"duplicate beat_id {value!r}")
    for value in duplicates([(b.scene_id, b.order) for b in beats]):
        result.add("error", "visual.order_duplicate", rel, f"two beats share scene/order {value}")
    pools = {
        "scene": {s.scene_id for s in result.scenes.scenes} if result.scenes else None,
        "asset": {a.asset_id: a for a in result.registry.assets} if result.registry else None,
        "source": {s.source_id for s in result.ledger.sources} if result.ledger else None,
        "claim": {c.claim_id for c in result.ledger.claims} if result.ledger else None,
    }
    for b in beats:
        loc = f"{rel}: {b.beat_id}"
        refs = [("scene", [b.scene_id]), ("asset", b.asset_ids), ("source", b.source_ids), ("claim", b.claim_ids)]
        for kind, ids in refs:
            pool = pools[kind]
            for ref in ids:
                if pool is not None and ref not in pool:
                    result.add("error", f"ref.missing_{kind}", loc, f"unknown {kind} {ref!r}")


def _check_status_gates(result: ValidationResult) -> None:
    """Statuses that assert human sign-off must be backed by the approval log."""
    status = result.manifest.project_status
    if status not in APPROVAL_REQUIRED or None in (result.scenes, result.ledger, result.approvals):
        return
    state = script_approval_state(result.approvals, script_fingerprint(result.scenes, result.ledger))
    if state.status != "approved":
        result.add("error", "project.status_requires_approval", MANIFEST_NAME,
                   f"project_status '{status}' requires a current script approval; script is "
                   f"{state.describe()}. Run 'pipeline script validate'.")
    if status is ProjectStatus.PUBLICATION_READY:
        report = build_report(result.ledger, result.scenes,
                              active_exceptions(result.approvals, result.ledger))
        blockers = list(report.blockers)
        if result.registry is not None:
            blockers += build_rights_report(result.registry, result.scenes, result.approvals,
                                            extra_used_ids(result.manifest, result.visuals)).blockers
        for f in blockers:
            result.add("error", "project.publication_blocked", f"{MANIFEST_NAME}: {f.subject}",
                       f"{f.code}: {f.message}")
        _check_qa_signoff(result)


QA_SIGNOFF_REPORT = "reports/qa-master_16x9.json"


def _check_qa_signoff(result: ValidationResult) -> None:
    """publication_ready needs a clean master QA report, still current, and signed off by a person."""
    def block(message: str) -> None:
        result.add("error", "project.qa_signoff_required", MANIFEST_NAME, message)

    path = safe_resolve(result.project_dir, QA_SIGNOFF_REPORT)
    if not path.is_file():
        return block("publication_ready needs a master QA report and sign-off; run 'pipeline qa report' "
                     "and 'pipeline qa signoff'")
    try:
        report = QAReport.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        return block(f"{QA_SIGNOFF_REPORT} is unreadable; run 'pipeline qa report' again")
    if report.blocker_count or report.open_warning_count:
        return block(f"the QA report has {report.blocker_count} blocker(s) and {report.open_warning_count} "
                     "open warning(s)")
    if None in (result.registry, result.visuals) or report.inputs_fingerprint != qa_inputs_fingerprint(
            result.manifest, result.scenes, result.ledger, result.registry, result.visuals):
        return block("the project changed after QA; run 'pipeline qa report' and sign off again")
    state = qa_signoff_state(result.approvals, report.fingerprint)
    if state != "current":
        return block(f"QA sign-off is {state}; run 'pipeline qa signoff'")
    if report.output_path is None or not Path(report.output_path).is_file():
        return block("the signed-off video is missing; render it again")


def _check_asset_files(result: ValidationResult, project_dir: Path, media_root: Path | None,
                       verify_checksums: bool) -> None:
    rel = result.manifest.paths.asset_registry
    for a in result.registry.assets:
        loc = f"{rel}: {a.asset_id}"
        if a.root is AssetRoot.MEDIA:
            if media_root is None:
                result.add("error", "asset.media_root_unset", loc,
                           "asset uses root 'media' but PIPELINE_MEDIA_ROOT is not set")
                continue
            base = media_root
        else:
            base = project_dir
        try:
            target = safe_resolve(base, a.path)
        except UnsafePathError as exc:
            result.add("error", "path.unsafe", loc, str(exc))
            continue
        if not target.is_file():
            result.add("error", "file.missing", loc, f"{a.path} not found under {a.root} root")
            continue
        if verify_checksums and sha256_file(target) != a.sha256:
            result.add("error", "asset.checksum_mismatch", loc,
                       f"{a.path} does not match its recorded sha256; the file changed or the "
                       "record is wrong")
