"""Project scaffolding and minimal validation.

Phase 1 writes a minimal ``project.json``. Phase 2 replaces the stub model
with the full typed manifest schema; ``schema_version`` lets it detect and
migrate these early files rather than silently reinterpreting them.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

MANIFEST_NAME = "project.json"
SCHEMA_VERSION = "0.1"
SUPPORTED_SCHEMA_VERSIONS = {"0.1"}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG_LEN = 64
PROJECT_SUBDIRS = ("research", "script", "assets", "narration", "renders", "reports")


class ProjectError(Exception):
    """A user-facing error about a project path or manifest."""


class ProjectStub(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_version: str
    project_id: str
    title: str
    project_status: str
    created_at: datetime


def validate_slug(slug: str) -> str:
    if not SLUG_RE.fullmatch(slug) or len(slug) > MAX_SLUG_LEN:
        raise ProjectError(
            f"Invalid project slug {slug!r}: use lowercase letters, digits and single hyphens "
            f"(max {MAX_SLUG_LEN} chars), e.g. 'why-boredom-disappeared'."
        )
    return slug


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
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_id": slug,
        "title": slug.replace("-", " ").title(),
        "project_status": "draft",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = project_dir / (MANIFEST_NAME + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    tmp.replace(project_dir / MANIFEST_NAME)
    return project_dir


def validate_project(path: Path) -> ProjectStub:
    """Validate a project folder's location and manifest; raise ProjectError on problems."""
    if not path.exists():
        raise ProjectError(f"{path} does not exist.")
    if not path.is_dir():
        raise ProjectError(f"{path} is not a directory; pass the project folder.")
    manifest_path = path / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ProjectError(f"{manifest_path} is missing. Create projects with 'pipeline project init'.")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectError(f"{manifest_path} is not valid JSON (line {exc.lineno}: {exc.msg}).") from exc
    if not isinstance(data, dict):
        raise ProjectError(f"{manifest_path} must contain a JSON object.")
    version = data.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ProjectError(
            f"Unsupported schema_version {version!r}; supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}."
        )
    try:
        stub = ProjectStub.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        raise ProjectError(f"{manifest_path} is invalid: {problems}") from exc
    validate_slug(stub.project_id)
    if stub.project_id != path.resolve().name:
        raise ProjectError(
            f"project_id {stub.project_id!r} does not match folder name {path.resolve().name!r}."
        )
    return stub
