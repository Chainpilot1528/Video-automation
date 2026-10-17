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
