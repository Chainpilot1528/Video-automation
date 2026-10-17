"""Command-line entry point: ``pipeline``.

Exit codes:
    0  success
    1  check or validation failure
    2  usage error (bad arguments; raised by Typer)
    3  command exists but its phase is not implemented yet
    4  configuration error
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import __version__
from .config import ConfigError, PipelineConfig, load_config
from .doctor import Status, has_failures, run_checks
from .logging_utils import configure_logging, get_logger
from .project import ProjectError, apply_migration, init_project, plan_migration, validate_project
from .schemas import export_json_schemas

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_IMPLEMENTED = 3
EXIT_CONFIG = 4

app = typer.Typer(help="Reckoning Self documentary production pipeline.", no_args_is_help=True,
                  add_completion=False)
project_app = typer.Typer(help="Create and validate projects.", no_args_is_help=True)
render_app = typer.Typer(help="Render videos from validated projects.", no_args_is_help=True)
schema_app = typer.Typer(help="Inspect and export data contracts.", no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(render_app, name="render")
app.add_typer(schema_app, name="schema")


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
