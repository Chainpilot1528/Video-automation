"""QA report: ``reports/qa-<profile>.json``, rewritten by each ``pipeline qa report`` (Phase 8).

Blockers must be fixed. Warnings must be fixed or waived by a named person
with a written rationale. A QA sign-off binds to this report's fingerprint,
so a new render or a changed project needs a fresh report and sign-off.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import SCHEMA_VERSION, AwareDatetime, NonEmptyStr, Record, Sha256, Slug
from .project import OutputProfileName

QASeverity = Literal["blocker", "warning", "info"]


class QACheck(Record):
    code: NonEmptyStr                 # e.g. audio.peak_high
    subject: NonEmptyStr              # what it is about: a scene, asset, file or "video"
    severity: QASeverity
    message: str
    waivable: bool = True             # warnings only; blockers are never waived here
    waived_by: str | None = None
    waiver_rationale: str = ""

    @property
    def check_id(self) -> str:
        return f"{self.code}@{self.subject}"

    @property
    def open(self) -> bool:
        """Still needs action: a blocker, or a warning nobody has waived."""
        return self.severity == "blocker" or (self.severity == "warning" and self.waived_by is None)


class QAMeasurements(Record):
    duration_seconds: float | None = None
    integrated_lufs: float | None = None
    true_peak_dbtp: float | None = None
    loudness_range_lu: float | None = None
    black_intervals: list[tuple[float, float]] = Field(default_factory=list)   # (start, duration)
    frozen_intervals: list[tuple[float, float]] = Field(default_factory=list)
    silent_intervals: list[tuple[float, float]] = Field(default_factory=list)


class QAReport(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    project_id: Slug
    profile: OutputProfileName
    generated_at: AwareDatetime
    pipeline_version: str
    render_report: str | None = None          # relative path of the render report checked
    output_path: str | None = None
    output_sha256: Sha256 | None = None
    inputs_fingerprint: Sha256                # project content the QA ran against
    media_analysed: bool = False
    measurements: QAMeasurements = Field(default_factory=QAMeasurements)
    checks: list[QACheck] = Field(default_factory=list)
    blocker_count: int = Field(ge=0)
    open_warning_count: int = Field(ge=0)
    fingerprint: Sha256                       # what a sign-off binds to
