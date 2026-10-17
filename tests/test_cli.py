import json

import pytest
from typer.testing import CliRunner

from reckoning_pipeline import doctor as doctor_mod
from reckoning_pipeline.cli import EXIT_CONFIG, EXIT_FAILED, EXIT_NOT_IMPLEMENTED, EXIT_OK, app
from reckoning_pipeline.doctor import GIB


@pytest.fixture
def runner(tmp_path, monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("PIPELINE_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("PIPELINE_PROJECTS_ROOT", str(tmp_path / "projects"))
    return CliRunner()


def test_no_args_shows_help(runner):
    result = runner.invoke(app, [])
    assert "doctor" in result.output


def test_version(runner):
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == EXIT_OK
    assert "0.1.0" in result.output


def test_doctor_fails_without_ffmpeg(runner, monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: None)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == EXIT_FAILED
    assert "[FAIL] ffmpeg" in result.output
    assert "docs/INSTALL.md" in result.output


def test_doctor_passes_with_tools(runner, monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda name: f"/opt/{name}")
    monkeypatch.setattr(doctor_mod, "_run_first_line", lambda args: "v1")
    monkeypatch.setattr(doctor_mod.shutil, "disk_usage", lambda p: (1, 0, 100 * GIB))
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == EXIT_OK, result.output
    assert "0 fail" in result.output


def test_project_init_and_validate(runner, tmp_path):
    result = runner.invoke(app, ["project", "init", "demo-film"])
    assert result.exit_code == EXIT_OK, result.output
    result = runner.invoke(app, ["project", "validate", str(tmp_path / "projects" / "demo-film")])
    assert result.exit_code == EXIT_OK
    assert "OK: demo-film" in result.output


def test_project_init_duplicate_fails(runner):
    assert runner.invoke(app, ["project", "init", "demo"]).exit_code == EXIT_OK
    result = runner.invoke(app, ["project", "init", "demo"])
    assert result.exit_code == EXIT_FAILED
    assert "already exists" in result.output


def test_project_init_bad_slug(runner):
    result = runner.invoke(app, ["project", "init", "../escape"])
    assert result.exit_code == EXIT_FAILED
    assert "Invalid project slug" in result.output


def test_validate_invalid_path(runner, tmp_path):
    result = runner.invoke(app, ["project", "validate", str(tmp_path / "missing")])
    assert result.exit_code == EXIT_FAILED
    assert "does not exist" in result.output


def test_validate_demo(runner):
    from conftest import DEMO
    result = runner.invoke(app, ["project", "validate", str(DEMO)])
    assert result.exit_code == EXIT_OK, result.output
    assert "4 scenes, 3 sources, 3 claims, 4 assets" in result.output


def test_validate_strict_fails_on_warnings(runner, demo, tmp_path):
    renamed = demo.rename(tmp_path / "renamed")
    assert runner.invoke(app, ["project", "validate", str(renamed)]).exit_code == EXIT_OK
    result = runner.invoke(app, ["project", "validate", str(renamed), "--strict"])
    assert result.exit_code == EXIT_FAILED
    assert "project.id_mismatch" in result.output


def test_migrate_dry_run_writes_nothing(runner, tmp_path):
    d = tmp_path / "old"
    d.mkdir()
    original = json.dumps({"schema_version": "0.1", "project_id": "old", "title": "Old",
                           "project_status": "draft", "created_at": "2026-10-17T15:37:03+00:00"})
    (d / "project.json").write_text(original)
    result = runner.invoke(app, ["project", "migrate", str(d), "--dry-run"])
    assert result.exit_code == EXIT_OK
    assert "[dry-run]" in result.output
    assert sorted(p.name for p in d.iterdir()) == ["project.json"]
    assert runner.invoke(app, ["project", "migrate", str(d)]).exit_code == EXIT_OK
    assert runner.invoke(app, ["project", "validate", str(d)]).exit_code == EXIT_OK


def test_render_preview_not_implemented(runner, tmp_path):
    result = runner.invoke(app, ["render", "preview", str(tmp_path)])
    assert result.exit_code == EXIT_NOT_IMPLEMENTED
    assert "Phase 7" in result.output


def test_missing_argument_is_usage_error(runner):
    assert runner.invoke(app, ["project", "validate"]).exit_code == 2


def test_bad_config_exit_code(runner, monkeypatch):
    monkeypatch.setenv("PIPELINE_LOG_LEVEL", "loud")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == EXIT_CONFIG
    assert "PIPELINE_LOG_LEVEL" in result.output


def test_json_logs_carry_context(runner, monkeypatch, capfd):
    monkeypatch.setenv("PIPELINE_LOG_FORMAT", "json")
    from reckoning_pipeline.logging_utils import configure_logging, get_logger
    configure_logging("INFO", "json")
    get_logger(project_id="demo", stage="test").info("hello", extra={"scene_id": "s01"})
    line = capfd.readouterr().err.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["project_id"] == "demo"
    assert record["stage"] == "test"
    assert record["scene_id"] == "s01"
    assert record["level"] == "INFO"
    assert "ts" in record


def test_research_report_and_strict(runner, demo):
    result = runner.invoke(app, ["research", "report", str(demo)])
    assert result.exit_code == EXIT_OK
    assert "claim.critical_unreviewed" in result.output
    assert runner.invoke(app, ["research", "report", str(demo), "--strict"]).exit_code == EXIT_FAILED
    data = json.loads(runner.invoke(app, ["research", "report", str(demo), "--json"]).output)
    assert data["blocker_count"] == 1


def test_research_review_and_script_approval_flow(runner, demo):
    assert runner.invoke(app, ["script", "validate", str(demo)]).exit_code == EXIT_FAILED
    for cid in ("claim-review-required", "claim-checksum-catches-changes", "claim-no-auto-publish"):
        r = runner.invoke(app, ["research", "review", str(demo), cid, "--status", "verified",
                                "--by", "Test Reviewer", "--note", "read the code"])
        assert r.exit_code == EXIT_OK, r.output
    r = runner.invoke(app, ["script", "validate", str(demo)])
    assert r.exit_code == EXIT_OK, r.output
    assert "not approved" in r.output
    r = runner.invoke(app, ["script", "approve", str(demo), "--by", "Test Reviewer"])
    assert r.exit_code == EXIT_OK, r.output
    assert "script_approved" in r.output
    assert "approved by Test Reviewer" in runner.invoke(app, ["script", "validate", str(demo)]).output
    r = runner.invoke(app, ["script", "revoke", str(demo), "--by", "Test Reviewer", "--reason", "redo"])
    assert r.exit_code == EXIT_OK and "in_research" in r.output


def test_review_rejects_unauthorized(runner, demo, monkeypatch):
    monkeypatch.setenv("PIPELINE_AUTHORIZED_REVIEWERS", "Asha, Nikhil")
    r = runner.invoke(app, ["research", "review", str(demo), "claim-no-auto-publish", "--status", "verified",
                            "--by", "Mallory"])
    assert r.exit_code == EXIT_FAILED and "AUTHORIZED" in r.output


def test_research_exception_cli(runner, demo):
    r = runner.invoke(app, ["research", "exception", str(demo), "claim-review-required", "--by", "Editor",
                            "--rationale", "short"])
    assert r.exit_code == EXIT_FAILED and "rationale" in r.output
    r = runner.invoke(app, ["research", "exception", str(demo), "claim-review-required", "--by", "Editor",
                            "--rationale", "Internal demo claim, checked against the code."])
    assert r.exit_code == EXIT_OK, r.output
    assert runner.invoke(app, ["script", "validate", str(demo)]).exit_code == EXIT_OK
    r = runner.invoke(app, ["research", "exception", str(demo), "claim-review-required", "--by", "Editor",
                            "--revoke"])
    assert r.exit_code == EXIT_OK
    assert runner.invoke(app, ["script", "validate", str(demo)]).exit_code == EXIT_FAILED


def test_research_import_cli(runner, demo, tmp_path):
    f = tmp_path / "in.json"
    f.write_text('{"claims": [{"claim_id": "new-claim", "text": "New", "claim_type": "factual", '
                 '"importance": "contextual"}]}')
    r = runner.invoke(app, ["research", "import", str(demo), str(f), "--dry-run"])
    assert r.exit_code == EXIT_OK and "[dry-run] add 1: new-claim" in r.output
    assert "new-claim" not in (demo / "research/ledger.json").read_text()
    assert runner.invoke(app, ["research", "import", str(demo), str(f)]).exit_code == EXIT_OK
    assert "new-claim" in (demo / "research/ledger.json").read_text()
    assert runner.invoke(app, ["research", "import", str(demo), str(f)]).exit_code == EXIT_FAILED


def test_research_bibliography_cli(runner, demo):
    r = runner.invoke(app, ["research", "bibliography", str(demo)])
    assert r.exit_code == EXIT_OK and "No public sources" in r.output
    r = runner.invoke(app, ["research", "bibliography", str(demo), "--include-internal", "--write"])
    assert "README.md" in r.output
    assert (demo / "reports/sources.md").is_file()


def test_research_suggest_without_provider(runner, demo):
    r = runner.invoke(app, ["research", "suggest", str(demo)])
    assert r.exit_code == EXIT_NOT_IMPLEMENTED and "Phase 9" in r.output


def test_commands_refuse_invalid_project(runner, tmp_path):
    r = runner.invoke(app, ["research", "report", str(tmp_path / "missing")])
    assert r.exit_code == EXIT_FAILED
