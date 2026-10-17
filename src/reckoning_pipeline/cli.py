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
from .project import ProjectError, init_project, validate_project

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NOT_IMPLEMENTED = 3
EXIT_CONFIG = 4

app = typer.Typer(help="Reckoning Self documentary production pipeline.", no_args_is_help=True,
                  add_completion=False)
project_app = typer.Typer(help="Create and validate projects.", no_args_is_help=True)
render_app = typer.Typer(help="Render videos from validated projects.", no_args_is_help=True)
app.add_typer(project_app, name="project")
app.add_typer(render_app, name="render")


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
def project_validate(path: Path = typer.Argument(..., help="Project folder")) -> None:
    """Validate a project folder and its manifest."""
    try:
        stub = validate_project(path)
    except ProjectError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(EXIT_FAILED)
    get_logger(project_id=stub.project_id, stage="project.validate").info("project valid")
    typer.echo(f"OK: {stub.project_id} (schema {stub.schema_version}, status {stub.project_status})")


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
