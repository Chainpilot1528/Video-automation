"""Narration support files: pronunciation overrides and the narration build report."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator

from .common import SCHEMA_VERSION, AwareDatetime, Identifier, NonEmptyStr, Record, Sha256, no_duplicates


class Pronunciation(Record):
    term: NonEmptyStr          # as written in narration/captions, e.g. "Ladakh"
    say_as: NonEmptyStr        # what the TTS voice should read, e.g. "Luh-dahk"
    case_sensitive: bool = False
    note: str = ""


class PronunciationList(Record):
    """``narration/pronunciations.json``. Applied to TTS input only, never to captions."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    overrides: list[Pronunciation] = Field(default_factory=list)

    @field_validator("overrides")
    @classmethod
    def _unique_terms(cls, value: list[Pronunciation]) -> list[Pronunciation]:
        no_duplicates([o.term.lower() for o in value], "overrides.term")
        return value

    def apply(self, text: str) -> str:
        # Longest terms first, so "New Delhi" wins over "Delhi".
        for o in sorted(self.overrides, key=lambda o: len(o.term), reverse=True):
            flags = 0 if o.case_sensitive else re.IGNORECASE
            text = re.sub(rf"(?<!\w){re.escape(o.term)}(?!\w)", o.say_as, text, flags=flags)
        return text


class ChunkReport(Record):
    scene_id: Identifier
    asset_id: Identifier
    route: Literal["imported", "tts"]
    path: str
    sha256: Sha256
    fingerprint: Sha256
    cached: bool
    duration_seconds: float
    sample_rate: int
    channels: int
    integrated_lufs: float | None = None
    true_peak_dbtp: float | None = None
    leading_silence_seconds: float = 0.0
    trailing_silence_seconds: float = 0.0
    warnings: list[str] = Field(default_factory=list)


class NarrationReport(Record):
    """``reports/narration.json``, rewritten on each build."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project_id: str
    built_at: AwareDatetime
    provider: str | None = None
    voice: str | None = None
    chunks: list[ChunkReport] = Field(default_factory=list)
    missing: list[Identifier] = Field(default_factory=list)  # scenes with narration text but no audio
    warnings: list[str] = Field(default_factory=list)
