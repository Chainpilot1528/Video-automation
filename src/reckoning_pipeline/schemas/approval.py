"""Approval log: ``approvals.json``. Append-only record of human decisions.

Current state is derived from the log, never stored separately. A script
approval is bound to a fingerprint of the narration and the claims it uses,
so any later edit makes the approval stale instead of silently carrying over.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .common import SCHEMA_VERSION, AwareDatetime, Identifier, NonEmptyStr, Record, Sha256


class ApprovalKind(StrEnum):
    SCRIPT_APPROVED = "script_approved"
    SCRIPT_APPROVAL_REVOKED = "script_approval_revoked"
    CLAIM_EXCEPTION = "claim_exception"
    CLAIM_EXCEPTION_REVOKED = "claim_exception_revoked"


class ApprovalEvent(Record):
    event_id: Identifier
    kind: ApprovalKind
    by: NonEmptyStr
    at: AwareDatetime
    rationale: str = ""
    fingerprint: Sha256 | None = None
    claim_id: Identifier | None = None

    @model_validator(mode="after")
    def _rules(self) -> "ApprovalEvent":
        claim_kinds = (ApprovalKind.CLAIM_EXCEPTION, ApprovalKind.CLAIM_EXCEPTION_REVOKED)
        if self.kind in claim_kinds and self.claim_id is None:
            raise ValueError(f"'{self.kind}' events need a claim_id")
        if self.kind not in claim_kinds and self.claim_id is not None:
            raise ValueError(f"'{self.kind}' events must not have a claim_id")
        if self.kind in (ApprovalKind.SCRIPT_APPROVED, ApprovalKind.CLAIM_EXCEPTION) \
                and self.fingerprint is None:
            raise ValueError(f"'{self.kind}' events must record the fingerprint they approve")
        if self.kind is ApprovalKind.CLAIM_EXCEPTION and len(self.rationale.strip()) < 20:
            raise ValueError("a claim exception needs a written rationale (at least 20 characters)")
        return self


class ApprovalLog(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    events: list[ApprovalEvent] = Field(default_factory=list)
