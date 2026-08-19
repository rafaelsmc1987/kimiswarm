"""Corpus primitives: SourceRecord and EvidenceSpan (plan §19 and §21)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ExtractionStatus,
    EvidenceType,
    PrimarySecondary,
    QualityGrade,
    RetractionStatus,
    SourceType,
)


class Locator(BaseModel):
    """A precise position inside a source (page/section/paragraph/table/line...)."""

    model_config = ConfigDict(extra="forbid")

    type: str = "locator"
    page: int | None = None
    section: str | None = None
    paragraph: int | None = None
    table: str | None = None
    figure: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    commit: str | None = None
    file: str | None = None
    uri_fragment: str | None = None


class SourceRecord(BaseModel):
    """Canonical, normalized representation of one document (plan §19).

    A ``SourceRecord`` is the identity anchor of the corpus layer. Every piece of
    evidence ultimately points back to one of these. Fields follow the JSON in
    §19 verbatim so the schema, prompts and gate code agree.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str
    canonical_uri: str
    title: str
    authors: list[str] = Field(default_factory=list)
    publisher: str | None = None
    date: datetime | None = None
    retrieved_at: datetime | None = None
    language: str | None = None
    source_type: SourceType = SourceType.UNKNOWN
    content_hash: str | None = None
    version: str | None = None
    primary_or_secondary: PrimarySecondary = PrimarySecondary.UNKNOWN
    quality_policy: str | None = None
    quality_grade: QualityGrade = QualityGrade.UNVERIFIED
    retraction_status: RetractionStatus = RetractionStatus.UNKNOWN
    conflicts_of_interest: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(
        default_factory=list,
        description="source_ids this source syndicates from / relies on.",
    )
    access_path: str | None = None
    extraction_status: ExtractionStatus = ExtractionStatus.NOT_EXTRACTED
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_dependent_on(self, other_id: str) -> bool:
        return other_id in self.dependencies


class EvidenceSpan(BaseModel):
    """The minimum unit of evidence: an exact, locatable span (plan §21).

    Exact verbatim spans are kept separate from summaries on purpose — a
    normalized proposition may paraphrase, but ``verbatim_span`` must be the
    literal text (or a literal table/number) as it appears in the source.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_id: str
    locator: Locator = Field(default_factory=Locator)
    verbatim_span: str = ""
    normalized_proposition: str | None = None
    evidence_type: EvidenceType = EvidenceType.VERBATIM
    extraction_method: str | None = None
    extractor: str | None = None
    verified: bool = False
    content_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def has_exact_span(self) -> bool:
        """A material claim must resolve to a non-empty exact span (DoD §44)."""
        return bool(self.verbatim_span.strip())
