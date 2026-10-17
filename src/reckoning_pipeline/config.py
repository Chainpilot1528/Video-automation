"""Validated pipeline configuration.

Values come from safe defaults, overridden by ``PIPELINE_*`` environment
variables. Paid providers and network access are off by default; nothing in
this module enables them implicitly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ENV_PREFIX = "PIPELINE_"


class ConfigError(ValueError):
    """Raised when configuration values are invalid."""


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    projects_root: Path = Field(default=Path("projects"))
    media_root: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["text", "json"] = "text"
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    min_free_disk_gb: float = Field(default=10.0, ge=0)
    warn_free_disk_gb: float = Field(default=25.0, ge=0)
    allow_network: bool = False
    allow_paid_providers: bool = False

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_level(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("log_format", mode="before")
    @classmethod
    def _lower_format(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("media_root", mode="before")
    @classmethod
    def _empty_media_root(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


_ENV_FIELDS = {
    "PROJECTS_ROOT": "projects_root",
    "MEDIA_ROOT": "media_root",
    "LOG_LEVEL": "log_level",
    "LOG_FORMAT": "log_format",
    "FFMPEG_PATH": "ffmpeg_path",
    "FFPROBE_PATH": "ffprobe_path",
    "MIN_FREE_DISK_GB": "min_free_disk_gb",
    "WARN_FREE_DISK_GB": "warn_free_disk_gb",
    "ALLOW_NETWORK": "allow_network",
    "ALLOW_PAID_PROVIDERS": "allow_paid_providers",
}


def load_config(env: Mapping[str, str] | None = None) -> PipelineConfig:
    """Build a config from defaults plus ``PIPELINE_*`` environment overrides."""
    env = os.environ if env is None else env
    values = {
        field: env[ENV_PREFIX + key]
        for key, field in _ENV_FIELDS.items()
        if ENV_PREFIX + key in env
    }
    try:
        config = PipelineConfig(**values)
    except ValidationError as exc:
        problems = "; ".join(
            f"{ENV_PREFIX}{_env_name(err['loc'][0])}: {err['msg']}" for err in exc.errors()
        )
        raise ConfigError(f"Invalid configuration: {problems}") from exc
    if config.warn_free_disk_gb < config.min_free_disk_gb:
        raise ConfigError(
            f"Invalid configuration: {ENV_PREFIX}WARN_FREE_DISK_GB must be >= "
            f"{ENV_PREFIX}MIN_FREE_DISK_GB"
        )
    return config


def _env_name(field: object) -> str:
    for key, name in _ENV_FIELDS.items():
        if name == field:
            return key
    return str(field).upper()
