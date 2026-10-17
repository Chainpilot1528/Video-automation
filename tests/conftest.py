import json
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "demo-project"


@pytest.fixture
def demo(tmp_path) -> Path:
    """A writable copy of the demo project, in a folder named after its project_id."""
    target = tmp_path / "demo-project"
    shutil.copytree(DEMO, target)
    return target


def edit_json(path: Path, mutate) -> None:
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data, indent=2))


@pytest.fixture
def runner_env(tmp_path, monkeypatch):
    """(CliRunner, app, cli module) with a clean PIPELINE_* environment."""
    import os

    from typer.testing import CliRunner

    from reckoning_pipeline import cli
    for key in list(os.environ):
        if key.startswith("PIPELINE_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("PIPELINE_PROJECTS_ROOT", str(tmp_path / "projects"))
    return CliRunner(), cli.app, cli
