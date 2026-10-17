"""Explicit schema migrations. Old fields are never silently reinterpreted.

Each migration maps known fields only; anything it does not understand makes
it refuse, so no data is dropped without the user seeing why.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ..schemas import ProjectManifest
from ..schemas.common import SCHEMA_VERSION
from ..schemas.project import ProjectStatus
from ..utils.fs import write_json_atomic
from .scaffold import MANIFEST_NAME, ProjectError, write_default_files

_V01_FIELDS = {"schema_version", "project_id", "title", "project_status", "created_at"}
_V01_STATUS = {"draft": ProjectStatus.DRAFT}


@dataclass
class MigrationPlan:
    project_dir: Path
    from_version: str
    to_version: str
    manifest: ProjectManifest
    backup_path: Path
    files_to_create: list[str] = field(default_factory=list)

    def describe(self) -> list[str]:
        lines = [
            f"Migrate {self.project_dir / MANIFEST_NAME}: schema {self.from_version} -> {self.to_version}",
            f"Back up original to {self.backup_path.name}",
        ]
        lines += [f"Create {rel}" for rel in self.files_to_create]
        return lines


def plan_migration(project_dir: Path) -> MigrationPlan:
    manifest_path = project_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ProjectError(f"{manifest_path} is missing.")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectError(f"{manifest_path} is not valid JSON (line {exc.lineno}: {exc.msg}).") from exc
    version = data.get("schema_version") if isinstance(data, dict) else None
    if version == SCHEMA_VERSION:
        raise ProjectError(f"{manifest_path} is already schema {SCHEMA_VERSION}; nothing to migrate.")
    if version != "0.1":
        raise ProjectError(f"No migration available from schema_version {version!r}.")

    unknown = set(data) - _V01_FIELDS
    if unknown:
        raise ProjectError(f"Refusing to migrate: unrecognised 0.1 fields {sorted(unknown)} would be lost.")
    status = _V01_STATUS.get(data.get("project_status"))
    if status is None:
        raise ProjectError(f"Refusing to migrate: unknown 0.1 project_status {data.get('project_status')!r}.")
    try:
        created = datetime.fromisoformat(data["created_at"])
        manifest = ProjectManifest(
            project_id=data["project_id"], title=data["title"], project_status=status,
            created_at=created, updated_at=created,
        )
    except (KeyError, ValueError) as exc:
        raise ProjectError(f"Refusing to migrate: 0.1 manifest is incomplete or invalid ({exc}).") from exc

    backup = project_dir / f"{MANIFEST_NAME}.v0.1.bak"
    if backup.exists():
        raise ProjectError(f"{backup} already exists; move it aside before migrating.")
    p = manifest.paths
    to_create = [rel for rel in (p.brief, p.script, p.research_ledger, p.scenes, p.asset_registry)
                 if not (project_dir / rel).exists()]
    return MigrationPlan(project_dir, "0.1", SCHEMA_VERSION, manifest, backup, to_create)


def apply_migration(plan: MigrationPlan) -> None:
    manifest_path = plan.project_dir / MANIFEST_NAME
    plan.backup_path.write_bytes(manifest_path.read_bytes())
    write_default_files(plan.project_dir, plan.manifest, only_missing=True)
    write_json_atomic(manifest_path, plan.manifest.model_dump(mode="json"))
