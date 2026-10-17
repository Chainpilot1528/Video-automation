from conftest import REPO

from reckoning_pipeline.schemas import json_schemas


def test_committed_json_schemas_are_current():
    """Regenerate with: .venv/bin/pipeline schema export docs/schemas"""
    for name, text in json_schemas().items():
        committed = REPO / "docs" / "schemas" / name
        assert committed.is_file(), f"missing {committed}"
        assert committed.read_text() == text, f"{name} is stale; re-run 'pipeline schema export'"
