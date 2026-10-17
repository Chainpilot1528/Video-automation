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
from .approvals import active_exceptions, append_event, check_reviewer, claim_fingerprint, load_log
from .project.validate import ValidationResult
from .providers.llm import ProviderUnavailableError, get_llm_provider
from .research import (
    LedgerError, build_bibliography, build_report, format_report, import_records, parse_import,
    review_claim, save_ledger,
)
from .schemas import export_json_schemas
from .schemas.approval import ApprovalKind
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
app.add_typer(project_app, name="project")
app.add_typer(render_app, name="render")
app.add_typer(schema_app, name="schema")
app.add_typer(research_app, name="research")
app.add_typer(script_app, name="script")


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
