"""Command-line entry point: ``pipeline``.

Exit codes:
    0  success
    1  check or validation failure
    2  usage error (bad arguments; raised by Typer)
    3  command exists but its phase is not implemented yet
    4  configuration error
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import typer
from pydantic import ValidationError

from . import __version__
from .config import ConfigError, PipelineConfig, load_config
from .doctor import Status, has_failures, run_checks
from .logging_utils import configure_logging, get_logger
from .project import ProjectError, apply_migration, init_project, plan_migration, validate_project
from .assets import (
    AssetReviewError, Decision, IntakeError, apply_intake, build_credits, build_rights_report,
    format_rights_report, plan_derivative, plan_intake, review_asset,
)
from .media.audio import Tools
from .media.tools import ToolNotFoundError
from .narration import BuildOptions, NarrationError, build_narration, take_asset_id
from .providers.tts import PROVIDERS, TTSError, get_tts_provider
from .subtitles import CaptionError, build_captions, check_cues, parse_srt
from .approvals import active_exceptions, append_event, check_reviewer, claim_fingerprint, load_log
from .project.validate import ValidationResult
from .providers.llm import ProviderUnavailableError, get_llm_provider
from .research import (
    LedgerError, build_bibliography, build_report, format_report, import_records, parse_import,
    review_claim, save_ledger,
)
from .schemas import export_json_schemas
from .schemas.approval import ApprovalKind
from .schemas.asset import AssetRoot, AssetType, CommercialUse, CreationMethod
from .schemas.research import ClaimStatus
from .script import ScriptError, approve_script, check_script, revoke_script_approval
from .utils.fs import safe_resolve, write_text_atomic

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_IMPLEMENTED = 3
EXIT_CONFIG = 4

app = typer.Typer(help="Reckoning Self documentary production pipeline.", no_args_is_help=True,
                  add_completion=False)
project_app = typer.Typer(help="Create and validate projects.", no_args_is_help=True)
render_app = typer.Typer(help="Render videos from validated projects.", no_args_is_help=True)
schema_app = typer.Typer(help="Inspect and export data contracts.", no_args_is_help=True)
research_app = typer.Typer(help="Sources, claims, reviews and the research report.", no_args_is_help=True)
script_app = typer.Typer(help="Script readiness and human approval.", no_args_is_help=True)
assets_app = typer.Typer(help="Asset intake, rights review and credits.", no_args_is_help=True)
narration_app = typer.Typer(help="Scene-by-scene narration: import, TTS, measurement.", no_args_is_help=True)
captions_app = typer.Typer(help="Build and check SRT captions.", no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(render_app, name="render")
app.add_typer(schema_app, name="schema")
app.add_typer(research_app, name="research")
app.add_typer(script_app, name="script")
app.add_typer(assets_app, name="assets")
app.add_typer(narration_app, name="narration")
app.add_typer(captions_app, name="captions")


def _config(ctx: typer.Context) -> PipelineConfig:
    return ctx.obj


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context, version: bool = typer.Option(False, "--version", help="Show version.")) -> None:
    if version:
        typer.echo(f"reckoning-pipeline {__version__}")
        raise typer.Exit(EXIT_OK)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(EXIT_OK)
    try:
        config = load_config()
    except ConfigError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_CONFIG)
    configure_logging(config.log_level, config.log_format)
    ctx.obj = config


_MARKS = {Status.PASS: "PASS", Status.WARN: "WARN", Status.FAIL: "FAIL"}


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Check tools, disk space and settings. Installs nothing."""
    results = run_checks(_config(ctx))
    for r in results:
        typer.echo(f"[{_MARKS[r.status]}] {r.name:<14} {r.detail}")
        if r.remedy and r.status is not Status.PASS:
            typer.echo(f"       {'':<14} -> {r.remedy}")
    counts = {s: sum(r.status is s for r in results) for s in Status}
    typer.echo(f"\n{counts[Status.PASS]} pass, {counts[Status.WARN]} warn, {counts[Status.FAIL]} fail")
    raise typer.Exit(EXIT_FAILED if has_failures(results) else EXIT_OK)


@project_app.command("init")
def project_init(ctx: typer.Context, slug: str = typer.Argument(..., help="e.g. why-boredom-disappeared")) -> None:
    """Create a new project folder under the projects root."""
    log = get_logger(project_id=slug, stage="project.init")
    try:
        path = init_project(slug, _config(ctx).projects_root)
    except ProjectError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_FAILED)
    log.info("project created at %s", path)
    typer.echo(f"Created {path}")


@project_app.command("validate")
def project_validate(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as failures."),
    skip_checksums: bool = typer.Option(False, "--skip-checksums", help="Do not hash asset files."),
) -> None:
    """Validate a project's manifests, references, paths and asset checksums."""
    result = validate_project(path, media_root=_config(ctx).media_root,
                              verify_checksums=not skip_checksums)
    for issue in result.issues:
        typer.echo(str(issue), err=True)
    project_id = result.manifest.project_id if result.manifest else path.name
    log = get_logger(project_id=project_id, stage="project.validate")
    failed = bool(result.errors) or (strict and bool(result.warnings))
    summary = f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)"
    if failed:
        log.warning("validation failed: %s", summary)
        typer.echo(f"INVALID: {project_id} ({summary})")
        raise typer.Exit(EXIT_FAILED)
    m, sc, led, reg = result.manifest, result.scenes, result.ledger, result.registry
    log.info("project valid")
    typer.echo(f"OK: {m.project_id} (schema {m.schema_version}, status {m.project_status}; "
               f"{len(sc.scenes)} scenes, {len(led.sources)} sources, {len(led.claims)} claims, "
               f"{len(reg.assets)} assets; {summary})")


@project_app.command("migrate")
def project_migrate(
    path: Path = typer.Argument(..., help="Project folder"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan without writing anything."),
) -> None:
    """Upgrade a project's manifest to the current schema, keeping a backup."""
    try:
        plan = plan_migration(path)
    except ProjectError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_FAILED)
    for line in plan.describe():
        typer.echo(("[dry-run] " if dry_run else "") + line)
    if dry_run:
        return
    apply_migration(plan)
    get_logger(project_id=plan.manifest.project_id, stage="project.migrate").info(
        "migrated %s -> %s", plan.from_version, plan.to_version)
    typer.echo("Done. Run 'pipeline project validate' next.")


@schema_app.command("export")
def schema_export(out_dir: Path = typer.Argument(Path("docs/schemas"), help="Output folder")) -> None:
    """Write JSON Schema files for every manifest type."""
    for written in export_json_schemas(out_dir):
        typer.echo(f"Wrote {written}")


def _fail(message: str) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(EXIT_FAILED)


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
    return str(exc)


def _load_valid(ctx: typer.Context, path: Path) -> ValidationResult:
    """Validate the project and stop with its errors if it is not valid."""
    result = validate_project(path, media_root=_config(ctx).media_root, verify_checksums=False)
    if not result.ok:
        for issue in result.errors:
            typer.echo(str(issue), err=True)
        _fail(f"{path} has {len(result.errors)} validation error(s); fix them first")
    return result


def _reviewer(ctx: typer.Context, by: str) -> str:
    try:
        check_reviewer(by, _config(ctx).authorized_reviewers)
    except ValueError as exc:
        _fail(str(exc))
    return by.strip()


@research_app.command("report")
def research_report(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
    strict: bool = typer.Option(False, "--strict", help="Exit 1 if there are blockers."),
) -> None:
    """Flag unsourced, unverified, disputed and weakly supported claims."""
    result = _load_valid(ctx, path)
    report = build_report(result.ledger, result.scenes, active_exceptions(result.approvals, result.ledger))
    typer.echo(json.dumps(report.to_dict(), indent=2) if as_json else format_report(report))
    if strict and report.blockers:
        raise typer.Exit(EXIT_FAILED)


@research_app.command("import")
def research_import(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    file: Path = typer.Argument(..., help="JSON file with 'sources' and/or 'claims'"),
    replace: bool = typer.Option(False, "--replace", help="Overwrite records with the same ID."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would change."),
) -> None:
    """Add sources and claims to the research ledger from a JSON file."""
    result = _load_valid(ctx, path)
    try:
        incoming = parse_import(file.read_text(encoding="utf-8"))
        ledger, summary = import_records(result.ledger, incoming, replace=replace)
    except (OSError, LedgerError) as exc:
        _fail(str(exc))
    prefix = "[dry-run] " if dry_run else ""
    typer.echo(f"{prefix}add {len(summary.added)}: {', '.join(summary.added) or '-'}")
    typer.echo(f"{prefix}replace {len(summary.replaced)}: {', '.join(summary.replaced) or '-'}")
    if not dry_run:
        save_ledger(path, result.manifest, ledger)
        typer.echo("Ledger updated. Run 'pipeline research report' next.")


@research_app.command("review")
def research_review(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    claim_id: str = typer.Argument(...),
    status: ClaimStatus = typer.Option(..., "--status", help="Your review decision."),
    by: str = typer.Option(..., "--by", help="Your name, recorded as reviewer."),
    note: str = typer.Option("", "--note", help="What you checked and why."),
    on: str = typer.Option("", "--date", help="Review date YYYY-MM-DD (default: today)."),
) -> None:
    """Record a human review decision on a claim."""
    result = _load_valid(ctx, path)
    reviewer = _reviewer(ctx, by)
    try:
        review_date = date.fromisoformat(on) if on else date.today()
        ledger = review_claim(result.ledger, claim_id, status=status, by=reviewer, on=review_date, note=note)
    except ValueError as exc:
        _fail(str(exc))
    save_ledger(path, result.manifest, ledger)
    get_logger(project_id=result.manifest.project_id, stage="research.review").info(
        "claim %s set to %s by %s", claim_id, status.value, reviewer)
    typer.echo(f"{claim_id}: {status.value} (reviewer {reviewer}, {review_date.isoformat()})")


@research_app.command("exception")
def research_exception(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    claim_id: str = typer.Argument(...),
    by: str = typer.Option(..., "--by", help="Authorized reviewer recording the exception."),
    rationale: str = typer.Option("", "--rationale", help="Why this claim may proceed unresolved."),
    revoke: bool = typer.Option(False, "--revoke", help="Withdraw an existing exception."),
) -> None:
    """Record (or revoke) an explicit exception for a blocking claim."""
    result = _load_valid(ctx, path)
    reviewer = _reviewer(ctx, by)
    claims = {c.claim_id: c for c in result.ledger.claims}
    if claim_id not in claims:
        _fail(f"unknown claim_id {claim_id!r}")
    try:
        if revoke:
            if claim_id not in active_exceptions(result.approvals, result.ledger):
                _fail(f"no active exception for {claim_id!r}")
            event = append_event(path, result.manifest, result.approvals,
                                 kind=ApprovalKind.CLAIM_EXCEPTION_REVOKED, by=reviewer,
                                 rationale=rationale, claim_id=claim_id)
        else:
            event = append_event(path, result.manifest, result.approvals,
                                 kind=ApprovalKind.CLAIM_EXCEPTION, by=reviewer, rationale=rationale,
                                 fingerprint=claim_fingerprint(claims[claim_id]), claim_id=claim_id)
    except ValueError as exc:
        _fail(_error_text(exc))
    typer.echo(f"Recorded {event.event_id}: {event.kind.value} for {claim_id} by {reviewer}")


@research_app.command("bibliography")
def research_bibliography(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    include_internal: bool = typer.Option(False, "--include-internal", help="Include internal documents."),
    write: bool = typer.Option(False, "--write", help="Also write reports/sources.md."),
) -> None:
    """Print the source list for the video description, in narration order."""
    result = _load_valid(ctx, path)
    bib = build_bibliography(result.ledger, result.scenes, include_internal=include_internal)
    text = bib.to_markdown(result.manifest.title)
    typer.echo(text, nl=False)
    for sid, reason in bib.skipped.items():
        typer.echo(f"skipped {sid}: {reason}", err=True)
    if write:
        out = safe_resolve(path, "reports/sources.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(out, text)
        typer.echo(f"Wrote {out}", err=True)


@research_app.command("suggest")
def research_suggest(ctx: typer.Context, path: Path = typer.Argument(..., help="Project folder")) -> None:
    """Ask an enabled LLM provider for claim suggestions (written to research/notes/)."""
    _load_valid(ctx, path)
    try:
        get_llm_provider(_config(ctx))
    except ProviderUnavailableError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_NOT_IMPLEMENTED)


@script_app.command("validate")
def script_validate(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    strict: bool = typer.Option(False, "--strict", help="Also fail on warnings."),
) -> None:
    """Check whether the script is ready for human approval."""
    result = _load_valid(ctx, path)
    check = check_script(result, result.approvals)
    for f in check.findings:
        typer.echo(str(f))
    warnings = sum(f.severity == "warning" for f in check.findings)
    typer.echo(f"\nNarration: {check.word_count} words (~{check.estimated_seconds:g} s at 150 wpm)")
    typer.echo(f"Approval: {check.approval.describe()}")
    typer.echo(f"{len(check.blockers)} blocker(s), {warnings} warning(s)")
    if check.blockers or (strict and warnings):
        raise typer.Exit(EXIT_FAILED)


@script_app.command("approve")
def script_approve(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    by: str = typer.Option(..., "--by", help="Your name, recorded as approver."),
    note: str = typer.Option("", "--note", help="Optional approval note."),
) -> None:
    """Record your approval of the current narration and the claims it uses."""
    result = _load_valid(ctx, path)
    try:
        event = approve_script(result, result.approvals, by=by, note=note,
                               authorized=_config(ctx).authorized_reviewers)
    except (ScriptError, ValueError) as exc:
        _fail(_error_text(exc))
    typer.echo(f"Script approved by {event.by} ({event.event_id}); status: {result.manifest.project_status}")


@script_app.command("revoke")
def script_revoke(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    by: str = typer.Option(..., "--by", help="Your name."),
    reason: str = typer.Option(..., "--reason", help="Why the approval is withdrawn."),
) -> None:
    """Withdraw the current script approval."""
    result = _load_valid(ctx, path)
    try:
        event = revoke_script_approval(result, result.approvals, by=by, reason=reason,
                                       authorized=_config(ctx).authorized_reviewers)
    except (ScriptError, ValueError) as exc:
        _fail(_error_text(exc))
    typer.echo(f"Approval revoked by {event.by} ({event.event_id}); status: {result.manifest.project_status}")


@assets_app.command("report")
def assets_report(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
    strict: bool = typer.Option(False, "--strict", help="Exit 1 if there are publication blockers."),
) -> None:
    """Group assets by publication status and list what blocks each one."""
    result = _load_valid(ctx, path)
    report = build_rights_report(result.registry, result.scenes, result.approvals)
    typer.echo(json.dumps(report.to_dict(), indent=2) if as_json else format_rights_report(report))
    if strict and report.blockers:
        raise typer.Exit(EXIT_FAILED)


@assets_app.command("add")
def assets_add(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    file: Path = typer.Argument(..., help="File to ingest (it is copied, never moved or changed)"),
    asset_id: str = typer.Option(..., "--id", help="New asset ID, e.g. s02-archive-photo"),
    asset_type: AssetType = typer.Option(..., "--type"),
    method: CreationMethod = typer.Option(..., "--method", help="How the asset was obtained."),
    source_url: str = typer.Option(None, "--source-url"),
    provider: str = typer.Option("", "--provider", help="Site, archive or service it came from."),
    creator: str = typer.Option("", "--creator"),
    rights_holder: str = typer.Option("", "--rights-holder"),
    license_name: str = typer.Option("", "--license", help="Exact licence name, e.g. 'CC BY 4.0'."),
    license_url: str = typer.Option("", "--license-url"),
    commercial_use: CommercialUse = typer.Option(CommercialUse.UNKNOWN, "--commercial-use"),
    attribution: str = typer.Option(None, "--attribution", help="Exact required attribution text."),
    no_attribution: bool = typer.Option(False, "--no-attribution", help="Licence requires no attribution."),
    evidence: str = typer.Option("", "--evidence", help="Where the rights decision comes from."),
    scenes: list[str] = typer.Option([], "--scene", help="Intended scene ID (repeatable)."),
    metadata: Path = typer.Option(None, "--metadata", help="JSON file with further asset fields."),
    media: bool = typer.Option(False, "--media", help="Store under PIPELINE_MEDIA_ROOT."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate and show the plan; copy nothing."),
) -> None:
    """Ingest a file you supply and record its source, licence and checksum."""
    result = _load_valid(ctx, path)
    if attribution is not None and no_attribution:
        _fail("use either --attribution or --no-attribution, not both")
    fields: dict = {}
    if metadata is not None:
        try:
            fields = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _fail(f"cannot read --metadata: {exc}")
        if not isinstance(fields, dict):
            _fail("--metadata must contain a JSON object")
    cli_fields = {
        "asset_id": asset_id, "type": asset_type, "creation_method": method, "source_url": source_url,
        "provider": provider, "creator": creator, "rights_holder": rights_holder,
        "license_name": license_name, "license_url": license_url, "rights_evidence": evidence,
        "intended_scene_ids": scenes,
    }
    fields.update({k: v for k, v in cli_fields.items() if v not in (None, "", [])})
    if commercial_use is not CommercialUse.UNKNOWN or "commercial_use" not in fields:
        fields["commercial_use"] = commercial_use
    if attribution is not None:
        fields.update(attribution_required=True, attribution_text=attribution)
    elif no_attribution:
        fields.update(attribution_required=False)
    config = _config(ctx)
    try:
        plan = plan_intake(path, result.registry, file, fields,
                           root=AssetRoot.MEDIA if media else AssetRoot.PROJECT, media_root=config.media_root)
        for line in plan.describe():
            typer.echo(("[dry-run] " if dry_run else "") + line)
        gaps = [g for g in plan.asset.approval_blockers() if not g.startswith("review_status")]
        for gap in gaps:
            typer.echo(f"  before approval: {gap}")
        if not dry_run:
            apply_intake(path, result.manifest, result.registry, plan, min_free_gb=config.min_free_disk_gb)
            typer.echo(f"Registered {plan.asset.asset_id}. It stays unapproved until 'pipeline assets review'.")
    except IntakeError as exc:
        _fail(str(exc))


@assets_app.command("derive")
def assets_derive(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    parent_id: str = typer.Argument(..., help="Original asset this file was made from"),
    file: Path = typer.Argument(..., help="The derived file (crop, conversion, edit)"),
    asset_id: str = typer.Option(..., "--id", help="New asset ID for the derivative"),
    notes: str = typer.Option("", "--notes", help="What was changed."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Register a derivative; it inherits the original's rights and needs its own review."""
    result = _load_valid(ctx, path)
    config = _config(ctx)
    try:
        plan = plan_derivative(path, result.registry, parent_id, file, asset_id, notes=notes,
                               media_root=config.media_root)
        for line in plan.describe():
            typer.echo(("[dry-run] " if dry_run else "") + line)
        if not dry_run:
            apply_intake(path, result.manifest, result.registry, plan, min_free_gb=config.min_free_disk_gb)
            typer.echo(f"Registered derivative {asset_id} of {parent_id}.")
    except IntakeError as exc:
        _fail(str(exc))


@assets_app.command("review")
def assets_review(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    asset_id: str = typer.Argument(...),
    decision: Decision = typer.Option(..., "--decision", help="approve or block"),
    by: str = typer.Option(..., "--by", help="Your name, recorded as reviewer."),
    note: str = typer.Option("", "--note", help="What you checked (required to block)."),
) -> None:
    """Record your rights decision on an asset."""
    result = _load_valid(ctx, path)
    try:
        asset, event = review_asset(path, result.manifest, result.registry, result.approvals, asset_id,
                                    decision=decision, by=by, note=note,
                                    authorized=_config(ctx).authorized_reviewers)
    except (AssetReviewError, ValueError) as exc:
        _fail(_error_text(exc))
    typer.echo(f"{asset_id}: {asset.publication_status} by {event.by} ({event.event_id})")


@assets_app.command("credits")
def assets_credits(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    write: bool = typer.Option(False, "--write", help="Also write reports/credits.md."),
) -> None:
    """Print exact attributions and licence credits for assets used in scenes."""
    result = _load_valid(ctx, path)
    credits = build_credits(result.registry, result.scenes)
    text = credits.to_markdown(result.manifest.title)
    typer.echo(text, nl=False)
    for aid, reason in credits.skipped.items():
        typer.echo(f"skipped {aid}: {reason}", err=True)
    if write:
        out = safe_resolve(path, "reports/credits.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomic(out, text)
        typer.echo(f"Wrote {out}", err=True)


def _tools(ctx: typer.Context) -> Tools:
    try:
        return Tools.from_config(_config(ctx))
    except ToolNotFoundError as exc:
        _fail(str(exc))


@narration_app.command("import")
def narration_import(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    scene_id: str = typer.Argument(..., help="Scene this recording narrates"),
    file: Path = typer.Argument(..., help="Audio file (copied, never changed)"),
    creator: str = typer.Option(..., "--creator", help="Who voiced it."),
    take: int = typer.Option(1, "--take", min=1, help="Take number; the highest take is used."),
    method: CreationMethod = typer.Option(CreationMethod.RECORDED, "--method",
                                          help="'recorded' (you recorded it) or 'user_supplied'."),
    rights_holder: str = typer.Option("", "--rights-holder", help="Defaults to the creator."),
    commercial_use: CommercialUse = typer.Option(CommercialUse.ALLOWED, "--commercial-use"),
    evidence: str = typer.Option("", "--evidence", help="E.g. 'Recorded by me for this film'."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Import a human narration recording for one scene."""
    result = _load_valid(ctx, path)
    if scene_id not in {s.scene_id for s in result.scenes.scenes}:
        _fail(f"unknown scene {scene_id!r}")
    fields = {"asset_id": take_asset_id(scene_id, take), "type": "narration", "creation_method": method,
              "creator": creator, "rights_holder": rights_holder or creator, "commercial_use": commercial_use,
              "attribution_required": False, "derivatives_allowed": True,
              "rights_evidence": evidence or f"Narration voiced by {creator}.",
              "intended_scene_ids": [scene_id]}
    config = _config(ctx)
    try:
        plan = plan_intake(path, result.registry, file, fields)
        for line in plan.describe():
            typer.echo(("[dry-run] " if dry_run else "") + line)
        if not dry_run:
            apply_intake(path, result.manifest, result.registry, plan, min_free_gb=config.min_free_disk_gb)
            typer.echo(f"Imported take {take} for {scene_id}. Run 'pipeline narration build' next.")
    except IntakeError as exc:
        _fail(str(exc))


@narration_app.command("voices")
def narration_voices(
    provider: str = typer.Option("macos-say", "--provider", help=f"One of: {', '.join(PROVIDERS)}"),
    locale: str = typer.Option("", "--locale", help="Filter, e.g. en_IN or en."),
) -> None:
    """List voices for a TTS provider."""
    try:
        tts = get_tts_provider(provider)
        voices = tts.list_voices()
    except TTSError as exc:
        _fail(str(exc))
    for v in voices:
        if v.locale.startswith(locale):
            typer.echo(f"{v.name:<32} {v.locale:<8} {v.description}")
    typer.echo(f"\nNote: {tts.license_note}" if not tts.commercial_use_cleared else "", err=True)


@narration_app.command("build")
def narration_build(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    provider: str = typer.Option(None, "--provider",
                                 help=f"TTS for scenes without imported narration: {', '.join(PROVIDERS)}"),
    voice: str = typer.Option(None, "--voice", help="TTS voice name."),
    rate: int = typer.Option(None, "--rate", min=80, max=300, help="TTS speaking rate (words/min)."),
    scenes: list[str] = typer.Option([], "--scene", help="Only these scenes (repeatable)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be built."),
) -> None:
    """Build, normalize and measure narration per scene; unchanged scenes are reused."""
    result = _load_valid(ctx, path)
    tts = None
    if provider:
        try:
            tts = get_tts_provider(provider)
        except TTSError as exc:
            _fail(str(exc))
        if not tts.commercial_use_cleared:
            typer.echo(f"note: {tts.license_note} Its output is registered as blocked from publication.",
                       err=True)
    options = BuildOptions(provider=tts, voice=voice, rate_wpm=rate, scene_ids=scenes or None, dry_run=dry_run)
    try:
        built = build_narration(result, _tools(ctx), options)
    except (NarrationError, ValueError) as exc:
        _fail(_error_text(exc))
    if dry_run:
        for c in built.plan:
            state = "cached" if c.cached else ("build" if c.route in ("imported", "tts") else "-")
            typer.echo(f"[dry-run] {c.scene.scene_id:<24} {c.route:<9} {state}")
        return
    for c in built.report.chunks:
        typer.echo(f"{c.scene_id:<24} {c.route:<9} {c.duration_seconds:7.2f} s  "
                   f"{c.integrated_lufs if c.integrated_lufs is not None else '-':>6} LUFS  "
                   f"{'cached' if c.cached else 'built'}")
        for w in c.warnings:
            typer.echo(f"    warning: {w}")
    for w in built.report.warnings:
        typer.echo(f"warning: {w}")
    total = sum(c.duration_seconds for c in built.report.chunks)
    typer.echo(f"\n{len(built.report.chunks)} chunk(s), {total:.1f} s of narration. Report: reports/narration.json")


@captions_app.command("build")
def captions_build(ctx: typer.Context, path: Path = typer.Argument(..., help="Project folder")) -> None:
    """Write approximate SRT captions from narration text and measured audio."""
    result = _load_valid(ctx, path)
    try:
        built = build_captions(result)
    except CaptionError as exc:
        _fail(str(exc))
    for w in built.warnings:
        typer.echo(f"warning: {w}")
    if built.errors:
        for e in built.errors:
            typer.echo(f"error: {e}", err=True)
        raise typer.Exit(EXIT_FAILED)
    typer.echo(f"Wrote {built.path} ({len(built.cues)} cues, {built.method} timing)")


@captions_app.command("validate")
def captions_validate(file: Path = typer.Argument(..., help="SRT file")) -> None:
    """Check an SRT file's structure, ordering and readability."""
    try:
        cues = parse_srt(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail(str(exc))
    errors, warnings = check_cues(cues)
    for w in warnings:
        typer.echo(f"warning: {w}")
    for e in errors:
        typer.echo(f"error: {e}", err=True)
    typer.echo(f"{len(cues)} cues, {len(errors)} error(s), {len(warnings)} warning(s)")
    if errors:
        raise typer.Exit(EXIT_FAILED)


@render_app.command("preview")
def render_preview(path: Path = typer.Argument(..., help="Project folder")) -> None:
    """Render a low-resolution preview (Phase 7)."""
    typer.echo("error: 'render preview' is not implemented yet (planned for Phase 7: "
               "timeline compiler and FFmpeg rendering).", err=True)
    raise typer.Exit(EXIT_NOT_IMPLEMENTED)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
