"""Research ledger: ``research/ledger.json`` holding sources and claims.

A source existing does not prove it supports a claim, so claim verification
is tracked on the claim, separately from the source record.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .common import SCHEMA_VERSION, Identifier, NonEmptyStr, Record, no_duplicates


class SourceType(StrEnum):
    JOURNAL_ARTICLE = "journal_article"
    PREPRINT = "preprint"
    BOOK = "book"
    REPORT = "report"
    DATASET = "dataset"
    NEWS = "news"
    INTERVIEW = "interview"
    ARCHIVE = "archive"
    GOVERNMENT_DOCUMENT = "government_document"
    WEBSITE = "website"
    VIDEO = "video"
    INTERNAL_DOCUMENT = "internal_document"
    OTHER = "other"


class SourceClass(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"


class SourceStatus(StrEnum):
    UNCHECKED = "unchecked"
    CHECKED = "checked"
    INACCESSIBLE = "inaccessible"
    RETRACTED = "retracted"


class Excerpt(Record):
    claim_id: Identifier
    text: NonEmptyStr
    locator: str = ""  # page, section, or timestamp


class Source(Record):
    source_id: Identifier
    title: NonEmptyStr
    authors: list[str] = Field(default_factory=list)
    publisher: str = ""
    url: str | None = None
    archive_id: str | None = None
    identifier: str | None = None  # DOI, ISBN, or repository path
    published_date: date | None = None
    accessed_date: date | None = None
    source_type: SourceType
    classification: SourceClass
    supported_claim_ids: list[Identifier] = Field(default_factory=list)
    excerpts: list[Excerpt] = Field(default_factory=list)
    reliability_notes: str = ""
    verification_status: SourceStatus = SourceStatus.UNCHECKED
    citation_text: str = ""
    usage_notes: str = ""

    @field_validator("supported_claim_ids")
    @classmethod
    def _unique(cls, value: list) -> list:
        return no_duplicates(value, "supported_claim_ids")

    @field_validator("url")
    @classmethod
    def _url_scheme(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("https://", "http://")):
            raise ValueError("url must start with https:// or http://")
        return value

    @model_validator(mode="after")
    def _rules(self) -> "Source":
        if not (self.url or self.archive_id or self.identifier):
            raise ValueError("a source needs at least one of url, archive_id, or identifier")
        stray = [e.claim_id for e in self.excerpts if e.claim_id not in self.supported_claim_ids]
        if stray:
            raise ValueError(f"excerpts reference claims not in supported_claim_ids: {stray}")
        if (self.published_date and self.accessed_date
                and self.accessed_date < self.published_date):
            raise ValueError("accessed_date is earlier than published_date")
        return self


class ClaimType(StrEnum):
    FACTUAL = "factual"
    STATISTICAL = "statistical"
    CAUSAL = "causal"
    QUOTATION = "quotation"
    HISTORICAL = "historical"
    INTERPRETIVE = "interpretive"
    SPECULATIVE = "speculative"


class Importance(StrEnum):
    CRITICAL = "critical"
    SUPPORTING = "supporting"
    CONTEXTUAL = "contextual"


class ClaimStatus(StrEnum):
    UNVERIFIED = "unverified"
    PARTIALLY_VERIFIED = "partially_verified"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class EvidenceBasis(StrEnum):
    """What kind of evidence the cited sources provide for a claim."""

    EXPERIMENTAL = "experimental"            # randomised or controlled experiment
    META_ANALYSIS = "meta_analysis"          # systematic review / meta-analysis
    QUASI_EXPERIMENTAL = "quasi_experimental"  # natural experiment, RDD, diff-in-diff
    OBSERVATIONAL = "observational"          # correlational / cohort / survey
    DOCUMENTARY = "documentary"              # primary records, archives, official data
    EXPERT_OPINION = "expert_opinion"
    ANECDOTAL = "anecdotal"


CORRELATIONAL_BASES = frozenset({EvidenceBasis.OBSERVATIONAL, EvidenceBasis.ANECDOTAL,
                                 EvidenceBasis.EXPERT_OPINION})


class ClaimOrigin(StrEnum):
    HUMAN = "human"
    IMPORTED = "imported"
    LLM_SUGGESTION = "llm_suggestion"


class Claim(Record):
    claim_id: Identifier
    text: NonEmptyStr
    claim_type: ClaimType
    importance: Importance
    source_ids: list[Identifier] = Field(default_factory=list)
    verification_status: ClaimStatus = ClaimStatus.UNVERIFIED
    caveats: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    reviewer: str | None = None
    review_date: date | None = None
    review_notes: str = ""
    evidence_basis: list[EvidenceBasis] = Field(default_factory=list)
    origin: ClaimOrigin = ClaimOrigin.HUMAN

    @field_validator("source_ids")
    @classmethod
    def _unique(cls, value: list) -> list:
        return no_duplicates(value, "source_ids")

    @model_validator(mode="after")
    def _review_rules(self) -> "Claim":
        status = self.verification_status
        if status is not ClaimStatus.UNVERIFIED and not (self.reviewer and self.review_date):
            raise ValueError(f"status '{status}' requires a human reviewer and review_date")
        if status in (ClaimStatus.VERIFIED, ClaimStatus.PARTIALLY_VERIFIED) and not self.source_ids:
            raise ValueError(f"status '{status}' requires at least one source_id")
        if status is ClaimStatus.DISPUTED and not self.counter_evidence:
            raise ValueError("status 'disputed' requires counter_evidence")
        return self


class ResearchLedger(Record):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    sources: list[Source] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
