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
from .media.audio import MediaError, Tools
from .media.tools import ToolNotFoundError
from .narration import BuildOptions, NarrationError, build_narration, take_asset_id
from .narration.build import voice_clearance
from .narration.styles import StyleError, get_preset, style_filters
from .providers.tts import PROVIDERS, TTSError, get_tts_provider
from .subtitles import CaptionError, build_captions, check_cues, parse_srt
from .graphics import GraphicError, render_graphic
from .providers.image import ImageProviderUnavailableError, get_image_provider
from .schemas.visual import GraphicSpec
from .visuals import build_visual_report, format_visual_report, write_placeholders, write_sheet
from .render import ProfileError, RenderError, plan_render
from .render import render as run_render
from .timeline import TimelineError
from .assets.checklist import ChecklistError, record_checklist
from .assets.intake import asset_file
from .assets.cutout import MODEL_NAME, CutoutError, cut_out, model_path, u2net_predictor
from .assets.stock import add_stock_item, existing_for
from .providers.stock import MUSEUMS, StockError, get_stock_provider, parse_ref
from .script.draft import DraftError, draft_script
from .approvals import active_exceptions, append_event, check_reviewer, claim_fingerprint, load_log
from .project.validate import STATUS_GATE_CODES, ValidationResult, extra_used_ids
from .qa import QAError, load_report, revoke_signoff, run_qa, sign_off, verdict, waive_warning, write_report
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
timeline_app = typer.Typer(help="Compile the render timeline without rendering.", no_args_is_help=True)
schema_app = typer.Typer(help="Inspect and export data contracts.", no_args_is_help=True)
research_app = typer.Typer(help="Sources, claims, reviews and the research report.", no_args_is_help=True)
script_app = typer.Typer(help="Script readiness and human approval.", no_args_is_help=True)
assets_app = typer.Typer(help="Asset intake, rights review and credits.", no_args_is_help=True)
narration_app = typer.Typer(help="Scene-by-scene narration: import, TTS, measurement.", no_args_is_help=True)
captions_app = typer.Typer(help="Build and check SRT captions.", no_args_is_help=True)
visuals_app = typer.Typer(help="Visual plan report, contact sheet and placeholders.", no_args_is_help=True)
graphics_app = typer.Typer(help="Deterministic original graphics (SVG).", no_args_is_help=True)
music_app = typer.Typer(help="Music beds: create, attach, remove.", no_args_is_help=True)
qa_app = typer.Typer(help="Automated QA, warning waivers and human sign-off.", no_args_is_help=True)
archive_app = typer.Typer(help="Public-domain museum images (The Met, Art Institute of Chicago; CC0).",
                          no_args_is_help=True)
stock_app = typer.Typer(help="Search and add licensed stock media (contacts the provider's API).",
                        no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(render_app, name="render")
app.add_typer(timeline_app, name="timeline")
app.add_typer(schema_app, name="schema")
app.add_typer(research_app, name="research")
app.add_typer(script_app, name="script")
app.add_typer(assets_app, name="assets")
app.add_typer(narration_app, name="narration")
app.add_typer(captions_app, name="captions")
app.add_typer(visuals_app, name="visuals")
app.add_typer(graphics_app, name="graphics")
app.add_typer(stock_app, name="stock")
app.add_typer(archive_app, name="archive")
app.add_typer(music_app, name="music")
app.add_typer(qa_app, name="qa")


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
def research_suggest(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    provider: str = typer.Option(None, "--provider", help="LLM provider (voicebox = local Qwen3)."),
) -> None:
    """Ask a local LLM to list claims worth researching (written to research/notes/, never the ledger)."""
    from .research.assist import SuggestionError, suggest_claims, write_suggestions
    result = _load_valid(ctx, path)
    try:
        llm = get_llm_provider(_config(ctx), provider)
    except ProviderUnavailableError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_NOT_IMPLEMENTED)
    brief = safe_resolve(path, result.manifest.paths.brief).read_text(encoding="utf-8")
    try:
        claims = suggest_claims(llm, brief)
    except (ProviderUnavailableError, SuggestionError) as exc:
        _fail(str(exc))
    out = write_suggestions(safe_resolve(path, "research/notes"), claims, llm.name)
    for c in claims:
        typer.echo(f"  {c.claim_id}: ({c.claim_type}, {c.importance}) {c.text}")
    typer.echo(f"Wrote {out}: {len(claims)} unverified suggestion(s). Find sources before importing any of them.")


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
    report = build_rights_report(result.registry, result.scenes, result.approvals,
                                 extra_used_ids(result.manifest, result.visuals))
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
    credits = build_credits(result.registry, result.scenes, extra_used_ids(result.manifest, result.visuals))
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
        tts = get_tts_provider(provider, load_config())
        voices = tts.list_voices()
    except (TTSError, ConfigError) as exc:
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
    rate: int = typer.Option(None, "--rate", min=80, max=300, help="TTS speaking rate (words/min), if supported."),
    speed: float = typer.Option(None, "--speed", min=0.5, max=2.0,
                                help="Tempo for TTS output without changing pitch, e.g. 0.87 = 13% slower."),
    style: str = typer.Option(None, "--style", help="Voice processing: none, documentary, annt or sage."),
    humanize: bool = typer.Option(None, "--humanize/--no-humanize",
                                  help="TTS sentence by sentence with natural pauses and room tone."),
    instruct: str = typer.Option(None, "--instruct", help="Delivery instruction (Qwen3 CustomVoice voices)."),
    preset: str = typer.Option(None, "--preset", help="Named voice preset: reckoner or sage (sets provider, voice, "
                                                      "speed, style and delivery; explicit options win)."),
    scenes: list[str] = typer.Option([], "--scene", help="Only these scenes (repeatable)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be built."),
) -> None:
    """Build, normalize and measure narration per scene; unchanged scenes are reused."""
    result = _load_valid(ctx, path)
    if preset:
        try:
            p = get_preset(preset)
        except StyleError as exc:
            _fail(str(exc))
        provider, voice = provider or p.provider, voice or p.voice
        speed = p.speed if speed is None else speed
        style = style or p.style
        humanize = p.humanize if humanize is None else humanize
        instruct = p.instruct if instruct is None else instruct
        typer.echo(f"preset {p.name}: {p.voice} via {p.provider}, speed {speed:g}, style {style}"
                   + (", humanized" if humanize else ""), err=True)
    speed = 1.0 if speed is None else speed
    style = style or "none"
    try:
        style_filters(style)
    except StyleError as exc:
        _fail(str(exc))
    tts = None
    if provider:
        try:
            tts = get_tts_provider(provider, _config(ctx))
            cleared, note, _ = voice_clearance(tts, voice) if voice else (True, "", "")
        except TTSError as exc:
            _fail(str(exc))
        if not cleared:
            typer.echo(f"note: {note} Its output is registered as blocked from publication.", err=True)
    options = BuildOptions(provider=tts, voice=voice, rate_wpm=rate, speed=speed, style=style,
                           humanize=bool(humanize), instruct=instruct or "", scene_ids=scenes or None,
                           dry_run=dry_run)
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


def _visual_report(result: ValidationResult):
    return build_visual_report(result.visuals, result.scenes, result.ledger, result.registry, result.approvals)


@visuals_app.command("report")
def visuals_report(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output."),
    strict: bool = typer.Option(False, "--strict", help="Exit 1 if any scene has gaps."),
) -> None:
    """List every scene's visual beats, unresolved gaps and questionable choices."""
    result = _load_valid(ctx, path)
    report = _visual_report(result)
    typer.echo(json.dumps(report.to_dict(), indent=2) if as_json else format_visual_report(report))
    if strict and report.gaps:
        raise typer.Exit(EXIT_FAILED)


@visuals_app.command("sheet")
def visuals_sheet(ctx: typer.Context, path: Path = typer.Argument(..., help="Project folder")) -> None:
    """Write reports/visuals.html, a contact sheet of scenes, beats and gaps."""
    result = _load_valid(ctx, path)
    out = write_sheet(result, _visual_report(result), media_root=_config(ctx).media_root)
    typer.echo(f"Wrote {out}")


@visuals_app.command("placeholders")
def visuals_placeholders(ctx: typer.Context, path: Path = typer.Argument(..., help="Project folder")) -> None:
    """Write labelled placeholder frames for unresolved beats (preview only, never published)."""
    result = _load_valid(ctx, path)
    written = write_placeholders(path, result.visuals.beats)
    for w in written:
        typer.echo(f"Wrote {w}")
    typer.echo(f"{len(written)} placeholder(s). They are blocked from master renders.")


@visuals_app.command("generate")
def visuals_generate(ctx: typer.Context, path: Path = typer.Argument(..., help="Project folder")) -> None:
    """Generate visuals for beats with generation requests (needs an enabled provider)."""
    _load_valid(ctx, path)
    try:
        get_image_provider(_config(ctx))
    except ImageProviderUnavailableError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_NOT_IMPLEMENTED)


@graphics_app.command("render")
def graphics_render(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    spec_file: Path = typer.Argument(..., help="Graphic spec JSON (title, bar_chart or timeline)"),
    creator: str = typer.Option("Reckoning Self", "--creator", help="Recorded as creator/rights holder."),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Render a graphic spec to SVG and register it as an original-graphic asset."""
    result = _load_valid(ctx, path)
    try:
        spec = GraphicSpec.model_validate_json(spec_file.read_text(encoding="utf-8"))
        rendered = render_graphic(path, result.manifest, result.registry, result.ledger, spec,
                                  spec_name=spec_file.name, creator=creator, dry_run=dry_run)
    except OSError as exc:
        _fail(str(exc))
    except (GraphicError, ValueError) as exc:
        _fail(_error_text(exc))
    if rendered.unchanged:
        typer.echo(f"{spec.asset_id}: unchanged ({rendered.path})")
    else:
        typer.echo(f"{'[dry-run] would write' if dry_run else 'Wrote'} {rendered.path} and registered "
                   f"{spec.asset_id} (pending rights review)")


def _validated_for_render(ctx: typer.Context, path: Path) -> ValidationResult:
    """Full validation including asset checksums: never render from changed files."""
    result = validate_project(path, media_root=_config(ctx).media_root, verify_checksums=True)
    if not result.ok:
        for issue in result.errors:
            typer.echo(str(issue), err=True)
        _fail(f"{path} has {len(result.errors)} validation error(s); fix them before rendering")
    return result


@timeline_app.command("build")
def timeline_build(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    profile: str = typer.Option("preview", "--profile", help="preview or master_16x9"),
) -> None:
    """Compile and write reports/timeline-<profile>.json (no rendering)."""
    result = _validated_for_render(ctx, path)
    try:
        plan, _ = plan_render(result, _tools(ctx), profile, media_root=_config(ctx).media_root)
    except (ProfileError, TimelineError) as exc:
        _fail(str(exc))
    for s in plan.scenes:
        kinds = ", ".join(f"{g.kind}{'+' + g.motion.value if g.motion.value != 'none' else ''}" for g in s.segments)
        typer.echo(f"{s.start:7.2f}  {s.duration:6.2f} s  {s.scene_id:<24} {kinds}")
    for w in plan.warnings:
        typer.echo(f"warning: {w}")
    typer.echo(f"\nTotal {plan.total_duration:.2f} s, {plan.placeholder_count} placeholder(s). "
               f"Wrote reports/timeline-{profile}.json")


def _render(ctx: typer.Context, path: Path, profile: str, burn_captions: bool, dry_run: bool) -> None:
    result = _validated_for_render(ctx, path)
    config = _config(ctx)
    log = get_logger(project_id=result.manifest.project_id, stage=f"render.{profile}")
    try:
        out = run_render(result, _tools(ctx), profile, media_root=config.media_root, burn_captions=burn_captions,
                         min_free_gb=config.min_free_disk_gb, dry_run=dry_run)
    except (ProfileError, TimelineError) as exc:
        _fail(str(exc))
    except RenderError as exc:
        log.error("render failed")
        _fail(str(exc))
    for w in out.plan.warnings:
        typer.echo(f"warning: {w}")
    if dry_run:
        typer.echo(f"[dry-run] {len(out.plan.scenes)} scenes, {out.plan.total_duration:.2f} s, "
                   f"{out.plan.placeholder_count} placeholder(s); timeline written to reports/timeline-{profile}.json")
        return
    log.info("rendered %d scene(s), reused %d", len(out.rendered), len(out.cached))
    typer.echo(f"Scenes rendered: {', '.join(out.rendered) or 'none'}; reused: {', '.join(out.cached) or 'none'}")
    typer.echo(f"Video: {out.output}{' (unchanged)' if out.final_cached else ''}")
    if out.captions:
        typer.echo(f"Captions: {out.captions}")
    typer.echo(f"Report: {out.report_path}")
    if out.plan.placeholder_count:
        typer.echo(f"note: contains {out.plan.placeholder_count} placeholder(s); preview only")


def _yes_no(value: str | None, flag: str) -> bool | None:
    if value is None:
        return None
    v = value.strip().lower()
    if v in ("yes", "y", "true"):
        return True
    if v in ("no", "n", "false"):
        return False
    _fail(f"{flag} must be yes or no")


@assets_app.command("checklist")
def assets_checklist(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    asset_id: str = typer.Argument(...),
    people: str = typer.Option(None, "--people", help="yes/no: identifiable people visible?"),
    people_clearance: str = typer.Option(None, "--people-clearance", help="Release, or why none is needed."),
    trademarks: str = typer.Option(None, "--trademarks", help="yes/no: logos or trademarks visible?"),
    trademark_notes: str = typer.Option(None, "--trademark-notes", help="How endorsement is avoided."),
    derivatives: str = typer.Option(None, "--derivatives", help="yes/no: editing permitted?"),
    platform_cleared: str = typer.Option(None, "--platform-cleared", help="yes/no: music/SFX cleared for YouTube?"),
) -> None:
    """Record what you checked by watching/inspecting an asset (needed before approval)."""
    result = _load_valid(ctx, path)
    answers = {k: v for k, v in {
        "identifiable_people": _yes_no(people, "--people"), "people_clearance": people_clearance,
        "trademarks_visible": _yes_no(trademarks, "--trademarks"), "trademark_notes": trademark_notes,
        "derivatives_allowed": _yes_no(derivatives, "--derivatives"),
        "platform_cleared": _yes_no(platform_cleared, "--platform-cleared"),
    }.items() if v is not None}
    try:
        asset = record_checklist(path, result.manifest, result.registry, asset_id, answers)
    except ChecklistError as exc:
        _fail(str(exc))
    gaps = [g for g in asset.approval_blockers() if not g.startswith("review_status")]
    typer.echo(f"{asset_id}: recorded {', '.join(answers)}")
    typer.echo("Ready for 'pipeline assets review'." if not gaps else "Still needed: " + "; ".join(gaps))


@stock_app.command("search")
def stock_search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="What to look for, e.g. 'empty office at night'"),
    kind: str = typer.Option("video", "--type", help="video or photo"),
    orientation: str = typer.Option("landscape", "--orientation", help="landscape, portrait or square"),
    count: int = typer.Option(10, "--count", min=1, max=40),
    provider: str = typer.Option("pexels", "--provider"),
    project: Path = typer.Option(None, "--project", help="Mark results already used in this project."),
) -> None:
    """Search stock media. Sends only the query to the provider; downloads nothing."""
    if kind not in ("video", "photo"):
        _fail("--type must be video or photo")
    registry = _load_valid(ctx, project).registry if project else None
    try:
        items = get_stock_provider(provider).search(query, kind, per_page=count, orientation=orientation or None)
    except StockError as exc:
        _fail(str(exc))
    if not items:
        typer.echo("No results.")
        return
    for it in items:
        used = existing_for(registry, it) if registry else None
        size = f"{it.width}x{it.height}" if it.width else "?"
        dur = f"{it.duration_seconds:5.1f}s" if it.duration_seconds else "      "
        typer.echo(f"{it.ref:<24} {size:>10} {dur} {it.creator[:24]:<24} {it.page_url}"
                   + (f"  [used as {used}]" if used else ""))
    typer.echo(f"\nAdd one with: pipeline stock add <project> {items[0].ref} --id <asset-id> --scene <scene-id>")


@stock_app.command("add")
def stock_add(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    ref: str = typer.Argument(..., help="e.g. pexels:video:1234567 (from 'stock search')"),
    asset_id: str = typer.Option(..., "--id", help="New asset ID"),
    scenes: list[str] = typer.Option([], "--scene", help="Intended scene (repeatable)."),
    media: bool = typer.Option(False, "--media", help="Store under PIPELINE_MEDIA_ROOT."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Look up and validate; download nothing."),
) -> None:
    """Download a stock item via the provider's API and register it (pending your rights review)."""
    result = _load_valid(ctx, path)
    config = _config(ctx)
    try:
        name, kind, item_id = parse_ref(ref)
        provider = get_stock_provider(name)
        item = provider.get(kind, item_id)
        added = add_stock_item(path, result.manifest, result.registry, provider, item, asset_id, scenes=scenes,
                               target_width=result.manifest.resolution.width, media_root=config.media_root,
                               use_media_root=media, min_free_gb=config.min_free_disk_gb, dry_run=dry_run)
    except (StockError, IntakeError) as exc:
        _fail(str(exc))
    c = added.chosen
    prefix = "[dry-run] " if dry_run else ""
    typer.echo(f"{prefix}{item.ref} by {item.creator}: {c.width}x{c.height} {c.file_type}"
               + (f", {added.bytes_downloaded / 1e6:.1f} MB" if not dry_run else ""))
    for line in added.plan.describe():
        typer.echo(prefix + line)
    if not dry_run:
        typer.echo(f"Next: watch it, then 'pipeline assets checklist {path} {asset_id} --people no --trademarks no' "
                   f"(with your real answers), then 'pipeline assets review'.")


@archive_app.command("search")
def archive_search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="What to look for, e.g. 'marble bust philosopher'"),
    source: str = typer.Option("met", "--source", help="met or aic"),
    count: int = typer.Option(10, "--count", min=1, max=20),
    project: Path = typer.Option(None, "--project", help="Mark results already used in this project."),
) -> None:
    """Search public-domain museum images. Sends only the query; downloads nothing."""
    if source not in MUSEUMS:
        _fail(f"--source must be one of: {', '.join(MUSEUMS)}")
    registry = _load_valid(ctx, project).registry if project else None
    try:
        items = get_stock_provider(source).search(query, "photo", per_page=count)
    except StockError as exc:
        _fail(str(exc))
    if not items:
        typer.echo("No public-domain results with images.")
        return
    for it in items:
        used = existing_for(registry, it) if registry else None
        x = it.extra
        typer.echo(f"{source}:{it.item_id:<9} {x.get('title', '')[:44]:<44} {x.get('artist', '')[:22]:<22} "
                   f"{x.get('date', '')[:16]:<16} {it.page_url}" + (f"  [used as {used}]" if used else ""))
    typer.echo(f"\nAdd one with: pipeline archive add <project> {source}:{items[0].item_id} --id <asset-id> "
               "--scene <scene-id>")


@archive_app.command("add")
def archive_add(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    ref: str = typer.Argument(..., help="e.g. met:436105 or aic:28560 (from 'archive search')"),
    asset_id: str = typer.Option(..., "--id", help="New asset ID"),
    scenes: list[str] = typer.Option([], "--scene", help="Intended scene (repeatable)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Look up and validate; download nothing."),
) -> None:
    """Download a public-domain museum image and register it (CC0; still pending your rights review)."""
    result = _load_valid(ctx, path)
    config = _config(ctx)
    try:
        name, _, item_id = parse_ref(ref, default_kind="photo")
        if name not in MUSEUMS:
            raise StockError(f"{name!r} isn't a museum source; use met:<id> or aic:<id>")
        provider = get_stock_provider(name)
        item = provider.get("photo", item_id)
        added = add_stock_item(path, result.manifest, result.registry, provider, item, asset_id, scenes=scenes,
                               target_width=10_000, media_root=config.media_root,
                               min_free_gb=config.min_free_disk_gb, dry_run=dry_run)
    except (StockError, IntakeError) as exc:
        _fail(str(exc))
    prefix = "[dry-run] " if dry_run else ""
    typer.echo(f"{prefix}{item.ref}: {item.description}"
               + (f" ({added.bytes_downloaded / 1e6:.1f} MB)" if not dry_run else ""))
    for line in added.plan.describe():
        typer.echo(prefix + line)


@archive_app.command("cutout")
def archive_cutout(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    parent_id: str = typer.Argument(..., help="Image asset to cut out, e.g. met-epicurus-head"),
    asset_id: str = typer.Option(..., "--id", help="New asset ID for the cut-out, e.g. met-epicurus-cut"),
    trim: bool = typer.Option(True, "--trim/--no-trim", help="Trim the PNG to the object (with a small margin)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Make the cut-out but register nothing."),
) -> None:
    """Remove an image's background (U²-Net, local) and register the transparent PNG as a derivative."""
    import tempfile

    result = _load_valid(ctx, path)
    config = _config(ctx)
    parent = next((a for a in result.registry.assets if a.asset_id == parent_id), None)
    if parent is None or parent.type is not AssetType.IMAGE:
        _fail(f"{parent_id!r} is not an image asset in this project")
    try:
        predict = u2net_predictor(model_path(config.models_dir))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"{asset_id}.png"
            w, h = cut_out(asset_file(path, parent, config.media_root), out, predict, trim=trim)
            plan = plan_derivative(path, result.registry, parent_id, out, asset_id, media_root=config.media_root,
                                   notes=f"Background removed from {parent_id} with {MODEL_NAME}"
                                         f"{', trimmed to the object' if trim else ''}. Check the edges "
                                         "before approving.")
            prefix = "[dry-run] " if dry_run else ""
            typer.echo(f"{prefix}cut-out {w}x{h} px")
            for line in plan.describe():
                typer.echo(prefix + line)
            if not dry_run:
                apply_intake(path, result.manifest, result.registry, plan, min_free_gb=config.min_free_disk_gb)
                typer.echo(f"Registered cut-out {asset_id} (derived from {parent_id}; pending your review).")
    except (CutoutError, IntakeError) as exc:
        _fail(str(exc))


@script_app.command("draft")
def script_draft(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    provider: str = typer.Option(None, "--provider", help="LLM provider: ollama or voicebox (both local)."),
    minutes: float = typer.Option(2.0, "--minutes", min=0.5, max=30, help="Target narration length."),
    model_size: str = typer.Option(None, "--model-size", help="Qwen3 size: 0.6B, 1.7B or 4B."),
) -> None:
    """Draft a script with a local AI from brief.md and the ledger (written to script/drafts/)."""
    result = _load_valid(ctx, path)
    config = _config(ctx)
    if model_size:
        config = config.model_copy(update={"llm_model_size": model_size})
    try:
        llm = get_llm_provider(config, provider)
        if getattr(llm, "sends_data_externally", False):
            typer.echo("note: this provider sends the brief and claims off this machine", err=True)
        out = draft_script(result, llm, minutes=minutes,
                           progress=lambda i, n, h: typer.echo(f"[{i}/{n}] drafting '{h}'...", err=True))
    except (ProviderUnavailableError, DraftError) as exc:
        _fail(str(exc))
    typer.echo(f"Draft: {out.path} ({out.words} words, {len(out.claims_used)} claims used)")
    for f in out.flags:
        typer.echo(f"  flag: {f}")
    typer.echo("Edit it, copy what you keep into script/script.md, then run 'pipeline script validate'.")


@music_app.command("pad")
def music_pad(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    asset_id: str = typer.Option("music-pad", "--id", help="New asset ID"),
    duration: float = typer.Option(None, "--duration", help="Seconds (default: narration length + 10 s)."),
    key: str = typer.Option("A", "--key", help="Root key: A, C, D or E."),
) -> None:
    """Synthesize an original ambient music bed (rights-clear) and register it."""
    from .assets.music_bed import create_pad
    result = _load_valid(ctx, path)
    if duration is None:
        spoken = sum((s.actual_narration_duration_seconds or s.planned_duration_seconds or 3.0)
                     for s in result.scenes.scenes)
        duration = round(spoken + 0.75 * len(result.scenes.scenes) + 10, 1)
    try:
        asset = create_pad(path, result.manifest, result.registry, _tools(ctx), asset_id, duration=duration, key=key)
    except (IntakeError, MediaError) as exc:
        _fail(str(exc))
    typer.echo(f"Created {asset.path} ({duration:g} s, key {key}); registered {asset.asset_id} (pending review)")


@music_app.command("set")
def music_set(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    asset_id: str = typer.Argument(..., help="Music asset to use as the bed"),
    gain_db: float = typer.Option(-14.0, "--gain-db", min=-40, max=0, help="Bed level before ducking."),
    no_duck: bool = typer.Option(False, "--no-duck", help="Don't lower the bed under narration."),
) -> None:
    """Put a music bed under the whole video (mixed after scenes are joined)."""
    from .assets.music_bed import set_music
    result = _load_valid(ctx, path)
    try:
        set_music(path, result.manifest, result.registry, asset_id, gain_db=gain_db, duck=not no_duck)
    except IntakeError as exc:
        _fail(str(exc))
    typer.echo(f"Music bed: {asset_id} at {gain_db:g} dB{'' if no_duck else ', ducked under narration'}")


@music_app.command("clear")
def music_clear(ctx: typer.Context, path: Path = typer.Argument(..., help="Project folder")) -> None:
    """Remove the music bed from the project (the asset itself is kept)."""
    from .assets.music_bed import set_music
    result = _load_valid(ctx, path)
    set_music(path, result.manifest, result.registry, None)
    typer.echo("Music bed removed")


@render_app.command("preview")
def render_preview(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    burn_captions: bool = typer.Option(False, "--burn-captions", help="Draw captions onto the picture."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Compile the timeline only."),
) -> None:
    """Render a fast 960x540 preview MP4 (placeholders allowed)."""
    _render(ctx, path, "preview", burn_captions, dry_run)


@render_app.command("master")
def render_master(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    burn_captions: bool = typer.Option(False, "--burn-captions", help="Draw captions onto the picture."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Compile the timeline only."),
) -> None:
    """Render the 16:9 master at project resolution (needs narration and no placeholders)."""
    _render(ctx, path, "master_16x9", burn_captions, dry_run)


@render_app.command("vertical")
def render_vertical(path: Path = typer.Argument(..., help="Project folder")) -> None:
    """9:16 derivatives (Phase 11, after the landscape master is approved)."""
    typer.echo("error: vertical renders come after the landscape master is approved (Phase 11).", err=True)
    raise typer.Exit(EXIT_NOT_IMPLEMENTED)


_QA_PROFILES = {"master": "master_16x9", "master_16x9": "master_16x9", "preview": "preview"}


def _qa_profile(name: str) -> str:
    if name not in _QA_PROFILES:
        _fail(f"unknown profile {name!r}; use master or preview")
    return _QA_PROFILES[name]


@qa_app.command("report")
def qa_report(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    profile: str = typer.Option("master", "--profile", help="master or preview: which render to check."),
    skip_media: bool = typer.Option(False, "--skip-media",
                                    help="Skip the FFmpeg loudness/black/frozen pass (can't be signed off)."),
) -> None:
    """Check the latest render and every publication gate; write reports/qa-<profile>.json and .md."""
    config = _config(ctx)
    name = _qa_profile(profile)
    result = validate_project(path, media_root=config.media_root, verify_checksums=True)
    if result.manifest is None:
        for issue in result.errors:
            typer.echo(str(issue), err=True)
        _fail(f"{path} has no readable project.json")
    report = run_qa(result, _tools(ctx), name, media_root=config.media_root, min_free_gb=config.min_free_disk_gb,
                    analyse_media=not skip_media)
    json_path, md_path = write_report(path, report)
    for k in report.checks:
        if k.severity == "blocker" or k.open:
            typer.echo(f"{k.severity.upper():<8} {k.check_id}: {k.message}")
    waived = sum(k.waived_by is not None for k in report.checks)
    typer.echo(f"\n{verdict(report)}: {report.blocker_count} blocker(s), {report.open_warning_count} open "
               f"warning(s), {waived} waived")
    typer.echo(f"Reports: {json_path} and {md_path}")
    if report.blocker_count:
        raise typer.Exit(EXIT_FAILED)


def _load_for_gate(ctx: typer.Context, path: Path) -> ValidationResult:
    """Like _load_valid, but tolerate the status-gate errors that sign-off and revoke exist to resolve."""
    result = validate_project(path, media_root=_config(ctx).media_root, verify_checksums=False)
    other = [i for i in result.errors if i.code not in STATUS_GATE_CODES]
    if not result.loaded:
        for issue in other:
            typer.echo(str(issue), err=True)
        _fail(f"{path} has {len(other)} validation error(s); fix them first")
    return result


def _qa_loaded(ctx: typer.Context, path: Path, profile: str):
    result = _load_for_gate(ctx, path)
    report = load_report(path, profile)
    if report is None:
        _fail(f"no {profile} QA report yet; run 'pipeline qa report {path}' first")
    return result, report


@qa_app.command("waive")
def qa_waive(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    check_id: str = typer.Argument(..., help="The warning's id, e.g. picture.frozen@41.2s (from the QA report)."),
    by: str = typer.Option(..., "--by", help="Your name, recorded with the waiver."),
    rationale: str = typer.Option(..., "--rationale", help="Why this warning is acceptable (20+ characters)."),
    profile: str = typer.Option("master", "--profile", help="master or preview."),
) -> None:
    """Accept one QA warning with a recorded rationale (blockers can't be waived)."""
    result, report = _qa_loaded(ctx, path, _qa_profile(profile))
    try:
        event = waive_warning(result, report, check_id, by=by, rationale=rationale,
                              authorized=_config(ctx).authorized_reviewers)
    except (QAError, ValueError) as exc:
        _fail(_error_text(exc))
    typer.echo(f"{check_id} waived by {event.by} ({event.event_id}). Run 'pipeline qa report' to refresh the report.")


@qa_app.command("signoff")
def qa_signoff(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    by: str = typer.Option(..., "--by", help="Your name, recorded as the reviewer."),
    checklist_done: bool = typer.Option(False, "--checklist-done",
                                        help="Confirm you completed the human review checklist."),
    note: str = typer.Option("", "--note", help="Optional note."),
) -> None:
    """Sign off a clean master QA report and mark the project publication_ready. Publishing stays manual."""
    result, report = _qa_loaded(ctx, path, "master_16x9")
    try:
        event = sign_off(result, report, by=by, checklist_done=checklist_done, note=note,
                         authorized=_config(ctx).authorized_reviewers)
    except (QAError, ValueError) as exc:
        _fail(_error_text(exc))
    typer.echo(f"QA signed off by {event.by} ({event.event_id}); status: publication_ready. "
               "Upload and publish manually.")


@qa_app.command("revoke")
def qa_revoke(
    ctx: typer.Context,
    path: Path = typer.Argument(..., help="Project folder"),
    by: str = typer.Option(..., "--by", help="Your name."),
    reason: str = typer.Option(..., "--reason", help="Why the sign-off is withdrawn."),
) -> None:
    """Withdraw the QA sign-off (status returns to in_review)."""
    result = _load_for_gate(ctx, path)
    try:
        event = revoke_signoff(result, by=by, reason=reason, authorized=_config(ctx).authorized_reviewers)
    except (QAError, ValueError) as exc:
        _fail(_error_text(exc))
    typer.echo(f"QA sign-off revoked by {event.by} ({event.event_id})")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
