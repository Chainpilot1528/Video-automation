"""Structured logging with project, stage, and scene context.

Usage::

    log = get_logger(project_id="why-boredom", stage="render")
    log.info("rendering scene", extra={"scene_id": "s03"})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

LOGGER_NAME = "reckoning_pipeline"
CONTEXT_FIELDS = ("project_id", "stage", "scene_id")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for name in CONTEXT_FIELDS:
            if not hasattr(record, name):
                setattr(record, name, None)
        return True


def _timestamp(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": _timestamp(record),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        for name in CONTEXT_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        context = " ".join(
            f"{name}={getattr(record, name)}"
            for name in CONTEXT_FIELDS
            if getattr(record, name, None) is not None
        )
        line = f"{_timestamp(record)} {record.levelname:<7} {record.getMessage()}"
        if context:
            line += f" [{context}]"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(level: str = "INFO", fmt: str = "text") -> logging.Logger:
    """Configure the package logger to write to stderr. Safe to call repeatedly."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    handler.addFilter(_ContextFilter())
    logger.addHandler(handler)
    return logger


def get_logger(**context: str) -> logging.LoggerAdapter:
    """Return a logger that stamps every record with the given context fields."""
    unknown = set(context) - set(CONTEXT_FIELDS)
    if unknown:
        raise ValueError(f"Unknown log context fields: {sorted(unknown)}")
    return _MergingAdapter(logging.getLogger(LOGGER_NAME), context)


class _MergingAdapter(logging.LoggerAdapter):
    """LoggerAdapter that lets per-call ``extra`` add to (not replace) context."""

    def process(self, msg, kwargs):
        kwargs["extra"] = {**self.extra, **kwargs.get("extra", {})}
        return msg, kwargs
