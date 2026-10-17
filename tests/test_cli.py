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
