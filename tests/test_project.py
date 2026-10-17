import json

import pytest

from reckoning_pipeline.project import (
    MANIFEST_NAME, PROJECT_SUBDIRS, ProjectError, init_project, validate_project, validate_slug,
)


@pytest.mark.parametrize("slug", ["", "Upper", "has space", "../escape", "a--b", "-lead", "trail-", "x" * 65, "a/b"])
def test_bad_slugs_rejected(slug):
    with pytest.raises(ProjectError):
        validate_slug(slug)


def test_init_creates_layout_and_manifest(tmp_path):
    path = init_project("why-boredom-disappeared", tmp_path)
    assert path == tmp_path.resolve() / "why-boredom-disappeared"
    for sub in PROJECT_SUBDIRS:
        assert (path / sub).is_dir()
    data = json.loads((path / MANIFEST_NAME).read_text())
    assert data["project_id"] == "why-boredom-disappeared"
    assert data["schema_version"] == "0.1"
    assert not list(path.glob("*.tmp"))


def test_init_refuses_existing(tmp_path):
    existing = tmp_path / "demo"
    existing.mkdir()
    (existing / "keep.txt").write_text("precious")
    with pytest.raises(ProjectError, match="already exists"):
        init_project("demo", tmp_path)
    assert (existing / "keep.txt").read_text() == "precious"


def test_validate_roundtrip(tmp_path):
    stub = validate_project(init_project("demo", tmp_path))
    assert stub.project_id == "demo"


def test_validate_missing_path(tmp_path):
    with pytest.raises(ProjectError, match="does not exist"):
        validate_project(tmp_path / "nope")


def test_validate_file_not_dir(tmp_path):
    f = tmp_path / "f.json"
    f.write_text("{}")
    with pytest.raises(ProjectError, match="not a directory"):
        validate_project(f)


def test_validate_missing_manifest(tmp_path):
    with pytest.raises(ProjectError, match="missing"):
        validate_project(tmp_path)


def _write_manifest(tmp_path, name, content):
    d = tmp_path / name
    d.mkdir()
    (d / MANIFEST_NAME).write_text(content)
    return d


def test_validate_bad_json(tmp_path):
    with pytest.raises(ProjectError, match="not valid JSON"):
        validate_project(_write_manifest(tmp_path, "demo", "{nope"))


def test_validate_unsupported_schema(tmp_path):
    with pytest.raises(ProjectError, match="Unsupported schema_version"):
        validate_project(_write_manifest(tmp_path, "demo", json.dumps({"schema_version": "9"})))


def test_validate_missing_fields(tmp_path):
    with pytest.raises(ProjectError, match="title"):
        validate_project(_write_manifest(tmp_path, "demo", json.dumps({"schema_version": "0.1", "project_id": "demo"})))


def test_validate_id_folder_mismatch(tmp_path):
    path = init_project("demo", tmp_path)
    renamed = path.rename(tmp_path / "other")
    with pytest.raises(ProjectError, match="does not match folder"):
        validate_project(renamed)
