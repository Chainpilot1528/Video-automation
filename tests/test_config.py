from pathlib import Path

import pytest

from reckoning_pipeline.config import ConfigError, load_config


def test_defaults_are_safe():
    config = load_config({})
    assert config.projects_root == Path("projects")
    assert config.media_root is None
    assert config.allow_network is False
    assert config.allow_paid_providers is False
    assert config.log_level == "INFO"


def test_env_overrides_and_normalisation():
    config = load_config({
        "PIPELINE_PROJECTS_ROOT": "/tmp/p",
        "PIPELINE_LOG_LEVEL": "debug",
        "PIPELINE_LOG_FORMAT": "JSON",
        "PIPELINE_MIN_FREE_DISK_GB": "5",
        "PIPELINE_ALLOW_NETWORK": "true",
        "PIPELINE_MEDIA_ROOT": "",
    })
    assert config.projects_root == Path("/tmp/p")
    assert config.log_level == "DEBUG"
    assert config.log_format == "json"
    assert config.min_free_disk_gb == 5
    assert config.allow_network is True
    assert config.media_root is None


def test_unrelated_env_vars_ignored():
    assert load_config({"HOME": "/x", "PIPELINE_UNKNOWN": "1"}).log_level == "INFO"


@pytest.mark.parametrize("key,value", [
    ("PIPELINE_LOG_LEVEL", "loud"),
    ("PIPELINE_LOG_FORMAT", "xml"),
    ("PIPELINE_MIN_FREE_DISK_GB", "-1"),
    ("PIPELINE_ALLOW_PAID_PROVIDERS", "maybe"),
])
def test_invalid_values_name_the_variable(key, value):
    with pytest.raises(ConfigError, match=key):
        load_config({key: value})


def test_warn_threshold_below_min_rejected():
    with pytest.raises(ConfigError, match="WARN_FREE_DISK_GB"):
        load_config({"PIPELINE_MIN_FREE_DISK_GB": "30", "PIPELINE_WARN_FREE_DISK_GB": "20"})
