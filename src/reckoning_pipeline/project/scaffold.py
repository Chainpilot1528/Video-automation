"""Create new projects with a valid, empty set of manifests."""

from __future__ import annotations

import re
from pathlib import Path

from ..schemas import AssetRegistry, ProjectManifest, ResearchLedger, SceneManifest
from ..schemas.common import MAX_SLUG_LEN, SLUG_PATTERN
from ..utils.fs import write_json_atomic, write_text_atomic

MANIFEST_NAME = "project.json"
PROJECT_SUBDIRS = ("research", "script", "assets", "narration", "renders", "reports")
_SLUG_RE = re.compile(SLUG_PATTERN)

BRIEF_TEMPLATE = """# Brief: {title}

## Central question

## Why it matters now

## Audience and promise

## Known risks (factual, legal, ethical)
"""

SCRIPT_TEMPLATE = """# Script draft: {title}

Editorial draft only. Approved narration lives in `scenes.json`, one scene at a time.

## Cold open / question

## Stakes and context

## Investigation

## Evidence and counter-evidence

## Resolution or honest uncertainty

## Source and visual notes
"""


class ProjectError(Exception):
    """A user-facing error about a project path or manifest."""


def validate_slug(slug: str) -> str:
    if not _SLUG_RE.fullmatch(slug) or len(slug) > MAX_SLUG_LEN:
        raise ProjectError(
            f"Invalid project slug {slug!r}: use lowercase letters, digits and single hyphens "
            f"(max {MAX_SLUG_LEN} chars), e.g. 'why-boredom-disappeared'."
        )
    return slug


def default_title(slug: str) -> str:
    return slug.replace("-", " ").title()


def write_default_files(project_dir: Path, manifest: ProjectManifest, *, only_missing: bool) -> list[Path]:
    """Write empty ledger/scenes/registry plus brief and script templates."""
    files = {
        manifest.paths.research_ledger: ResearchLedger().model_dump(mode="json"),
        manifest.paths.scenes: SceneManifest().model_dump(mode="json"),
        manifest.paths.asset_registry: AssetRegistry().model_dump(mode="json"),
    }
    texts = {
        manifest.paths.brief: BRIEF_TEMPLATE.format(title=manifest.title),
        manifest.paths.script: SCRIPT_TEMPLATE.format(title=manifest.title),
    }
    written = []
    for rel, data in {**files, **texts}.items():
        target = project_dir / rel
        if target.exists():
            if only_missing:
                continue
            raise ProjectError(f"{target} already exists; not overwriting it.")
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            write_text_atomic(target, data)
        else:
            write_json_atomic(target, data)
        written.append(target)
    return written


def init_project(slug: str, projects_root: Path) -> Path:
    """Create a new project folder. Refuses to touch an existing path."""
    validate_slug(slug)
    root = projects_root.resolve()
    project_dir = (root / slug).resolve()
    if project_dir.parent != root:
        raise ProjectError(f"Refusing to create project outside {root}.")
    if project_dir.exists():
        raise ProjectError(f"{project_dir} already exists; not overwriting it.")

    root.mkdir(parents=True, exist_ok=True)
    project_dir.mkdir()
    for sub in PROJECT_SUBDIRS:
        (project_dir / sub).mkdir()
    manifest = ProjectManifest(project_id=slug, title=default_title(slug))
    write_default_files(project_dir, manifest, only_missing=False)
    write_json_atomic(project_dir / MANIFEST_NAME, manifest.model_dump(mode="json"))
    return project_dir
