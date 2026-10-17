import os

from conftest import DEMO, edit_json

from reckoning_pipeline.project import validate_project


def codes(result, severity="error"):
    return [i.code for i in result.issues if i.severity == severity]


def test_demo_project_is_valid():
    result = validate_project(DEMO)
    assert result.ok, [str(i) for i in result.issues]
    assert not result.warnings
    assert len(result.scenes.scenes) == 4


def test_missing_path_and_file(tmp_path):
    assert codes(validate_project(tmp_path / "nope")) == ["path.missing"]
    f = tmp_path / "f.json"
    f.write_text("{}")
    assert codes(validate_project(f)) == ["path.not_directory"]
    assert codes(validate_project(tmp_path)) == ["file.missing"]


def test_bad_json(demo):
    (demo / "scenes.json").write_text("{nope")
    assert "json.invalid" in codes(validate_project(demo))


def test_old_schema_version_suggests_migration(demo):
    edit_json(demo / "project.json", lambda d: d.update(schema_version="0.1"))
    result = validate_project(demo)
    assert codes(result) == ["schema.unsupported_version"]
    assert "migrate" in result.issues[0].message


def test_unknown_schema_version(demo):
    edit_json(demo / "scenes.json", lambda d: d.update(schema_version="9.9"))
    assert "schema.unsupported_version" in codes(validate_project(demo))


def test_schema_error_names_the_record(demo):
    edit_json(demo / "scenes.json", lambda d: d["scenes"][1].update(order=0))
    issue = next(i for i in validate_project(demo).issues if i.code == "schema.invalid")
    assert "scenes[1](s02-claim-ledger).order" in issue.location


def test_duplicate_ids_and_orders(demo):
    def dup(d):
        d["scenes"][1]["scene_id"] = "s01-cold-open"
        d["scenes"][2]["order"] = 1
    edit_json(demo / "scenes.json", dup)
    found = codes(validate_project(demo))
    assert "id.duplicate" in found and "scene.order_duplicate" in found


def test_duplicate_claim_and_asset_ids(demo):
    edit_json(demo / "research/ledger.json",
              lambda d: d["claims"].append({**d["claims"][0]}))
    edit_json(demo / "assets/registry.json",
              lambda d: d["assets"].append({**d["assets"][0], "path": "assets/graphics/s02_claim_ledger.svg"}))
    found = codes(validate_project(demo))
    assert found.count("id.duplicate") == 2
    assert "asset.path_duplicate" in found


def test_missing_references(demo):
    def bad(d):
        scene = d["scenes"][0]
        scene["asset_ids"].append("ghost-asset")
        scene.setdefault("source_ids", []).append("ghost-source")
        scene.setdefault("claim_ids", []).append("ghost-claim")
    edit_json(demo / "scenes.json", bad)
    edit_json(demo / "assets/registry.json", lambda d: d["assets"][0].update(intended_scene_ids=["ghost"]))
    found = codes(validate_project(demo))
    for code in ("ref.missing_asset", "ref.missing_source", "ref.missing_claim", "ref.missing_scene"):
        assert code in found


def test_ledger_internal_references(demo):
    edit_json(demo / "research/ledger.json", lambda d: d["claims"][0].update(source_ids=["nowhere"]))
    found = codes(validate_project(demo))
    assert "ref.missing_source" in found


def test_ledger_asymmetry_is_a_warning(demo):
    edit_json(demo / "research/ledger.json", lambda d: d["sources"][0].update(supported_claim_ids=[], excerpts=[]))
    result = validate_project(demo)
    assert result.ok
    assert "ledger.asymmetric" in codes(result, "warning")


def test_narration_must_be_audio(demo):
    edit_json(demo / "scenes.json", lambda d: d["scenes"][0].update(narration_asset_id="s01-title"))
    assert "ref.wrong_asset_type" in codes(validate_project(demo))


def test_unused_asset_warning(demo):
    edit_json(demo / "assets/registry.json", lambda d: d["assets"][0].update(intended_scene_ids=[]))
    edit_json(demo / "scenes.json", lambda d: d["scenes"][0].update(asset_ids=[]))
    assert "asset.unused" in codes(validate_project(demo), "warning")


def test_unsafe_manifest_path(demo):
    edit_json(demo / "project.json", lambda d: d["paths"].update(scenes="../outside.json"))
    assert "schema.invalid" in codes(validate_project(demo))


def test_symlink_escape_is_unsafe(demo, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text('{"schema_version": "1.0", "scenes": []}')
    (demo / "scenes.json").unlink()
    os.symlink(outside, demo / "scenes.json")
    assert "path.unsafe" in codes(validate_project(demo))


def test_missing_brief_and_asset_file(demo):
    (demo / "brief.md").unlink()
    (demo / "assets/graphics/s01_title.svg").unlink()
    assert codes(validate_project(demo)).count("file.missing") == 2


def test_checksum_mismatch(demo):
    with (demo / "assets/graphics/s02_claim_ledger.svg").open("a") as fh:
        fh.write("<!-- edited -->")
    assert "asset.checksum_mismatch" in codes(validate_project(demo))
    assert validate_project(demo, verify_checksums=False).ok


def test_media_root_assets(demo, tmp_path):
    edit_json(demo / "assets/registry.json", lambda d: d["assets"][0].update(root="media"))
    assert "asset.media_root_unset" in codes(validate_project(demo))
    media = tmp_path / "media"
    (media / "assets/graphics").mkdir(parents=True)
    (media / "assets/graphics/s01_title.svg").write_bytes((demo / "assets/graphics/s01_title.svg").read_bytes())
    assert validate_project(demo, media_root=media).ok


def test_folder_name_mismatch_is_warning(demo, tmp_path):
    renamed = demo.rename(tmp_path / "renamed")
    result = validate_project(renamed)
    assert result.ok
    assert "project.id_mismatch" in codes(result, "warning")
