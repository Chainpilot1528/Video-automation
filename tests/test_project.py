import json

import pytest

from reckoning_pipeline.project import (
    MANIFEST_NAME, PROJECT_SUBDIRS, ProjectError, apply_migration, init_project, plan_migration,
    validate_project, validate_slug,
)

V01 = {"schema_version": "0.1", "project_id": "old", "title": "Old",
       "project_status": "draft", "created_at": "2026-10-17T15:37:03+00:00"}


@pytest.mark.parametrize("slug", ["", "Upper", "has space", "../escape", "a--b", "-lead", "trail-", "x" * 65, "a/b"])
def test_bad_slugs_rejected(slug):
    with pytest.raises(ProjectError):
        validate_slug(slug)


def test_init_creates_valid_project(tmp_path):
    path = init_project("why-boredom-disappeared", tmp_path)
    assert path == tmp_path.resolve() / "why-boredom-disappeared"
    for sub in PROJECT_SUBDIRS:
        assert (path / sub).is_dir()
    data = json.loads((path / MANIFEST_NAME).read_text())
    assert data["schema_version"] == "1.0"
    assert not list(path.rglob("*.tmp"))
    result = validate_project(path)
    assert result.ok and not result.warnings


def test_init_refuses_existing(tmp_path):
    existing = tmp_path / "demo"
    existing.mkdir()
    (existing / "keep.txt").write_text("precious")
    with pytest.raises(ProjectError, match="already exists"):
        init_project("demo", tmp_path)
    assert (existing / "keep.txt").read_text() == "precious"


def _v01_project(tmp_path, data=None):
    d = tmp_path / "old"
    d.mkdir()
    (d / MANIFEST_NAME).write_text(json.dumps(data or V01))
    return d


def test_migrate_v01_to_v1(tmp_path):
    d = _v01_project(tmp_path)
    plan = plan_migration(d)
    assert plan.from_version == "0.1" and plan.to_version == "1.0"
    apply_migration(plan)
    assert json.loads((d / "project.json.v0.1.bak").read_text()) == V01
    result = validate_project(d)
    assert result.ok, [str(i) for i in result.issues]
    assert result.manifest.created_at.isoformat() == V01["created_at"]


def test_migrate_keeps_existing_files(tmp_path):
    d = _v01_project(tmp_path)
    (d / "brief.md").write_text("my notes")
    plan = plan_migration(d)
    assert "brief.md" not in plan.files_to_create
    apply_migration(plan)
    assert (d / "brief.md").read_text() == "my notes"


@pytest.mark.parametrize("data,match", [
    ({**V01, "extra": 1}, "unrecognised"),
    ({**V01, "project_status": "weird"}, "project_status"),
    ({k: v for k, v in V01.items() if k != "title"}, "incomplete"),
    ({**V01, "schema_version": "1.0"}, "already"),
    ({**V01, "schema_version": "0.0"}, "No migration"),
])
def test_migrate_refuses(tmp_path, data, match):
    with pytest.raises(ProjectError, match=match):
        plan_migration(_v01_project(tmp_path, data))


def test_migrate_refuses_when_backup_exists(tmp_path):
    d = _v01_project(tmp_path)
    (d / "project.json.v0.1.bak").write_text("older")
    with pytest.raises(ProjectError, match="already exists"):
        plan_migration(d)
