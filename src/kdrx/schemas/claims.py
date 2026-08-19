"""Claim-evidence graph primitives (plan §22, §23, §25)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ClaimImportance,
    ClaimType,
    ContradictionStatus,
    ContradictionType,
    EdgeDirectness,
    EdgeRelation,
    Standing,
)


class FalsificationCriteria(BaseModel):
    """What would count as evidence against a claim."""

    model_config = ConfigDict(extra="forbid")

    criterion: str
    detector: str | None = None
    trigger_value: Any | None = None


class Claim(BaseModel):
    """An atomic, falsifiable claim (plan §22).

    Compound sentences are decomposed into multiple atomic claims before
    standing is computed. ``scope`` constrains populations/samples/time/geography
    so support edges can be checked for scope match.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    statement: str
    scope: dict[str, Any] = Field(default_factory=dict)
    claim_type: ClaimType = ClaimType.DESCRIPTIVE
    importance: ClaimImportance = ClaimImportance.MAJOR
    falsification_criteria: list[FalsificationCriteria] = Field(default_factory=list)
    support_edges: list[str] = Field(default_factory=list)
    contradiction_edges: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    standing: Standing = Standing.UNRESOLVED
    confidence: float = 0.0
    calibration_basis: str | None = None
    report_locations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimEvidenceEdge(BaseModel):
    """A directed relation between one claim and one evidence span (plan §23)."""

    model_config = ConfigDict(extra="forbid")

    edge_id: str
    claim_id: str
    evidence_id: str
    relation: EdgeRelation
    directness: EdgeDirectness = EdgeDirectness.DIRECT
    entailment: float = Field(ge=0.0, le=1.0, default=0.0)
    source_quality: float = Field(ge=0.0, le=1.0, default=0.0)
    independence: float = Field(ge=0.0, le=1.0, default=0.0)
    scope_match: bool = False
    temporal_match: bool = False
    verifier: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    limitations: list[str] = Field(default_factory=list)

    def is_supportive(self) -> bool:
        return self.relation in (
            EdgeRelation.SUPPORTS,
            EdgeRelation.PARTIALLY_SUPPORTS,
        )

    def is_contradicting(self) -> bool:
        return self.relation == EdgeRelation.CONTRADICTS


class ContradictionCluster(BaseModel):
    """A cluster of claims/sources that disagree (plan §25)."""

    model_config = ConfigDict(extra="forbid")

    contradiction_id: str
    claims: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    atomic_disagreement: str | None = None
    contradiction_type: ContradictionType = ContradictionType.FACTUAL
    possible_resolution: str | None = None
    new_searches_required: list[str] = Field(default_factory=list)
    status: ContradictionStatus = ContradictionStatus.OPEN
    resolution_evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
