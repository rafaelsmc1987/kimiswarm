"""Intake and the research contract (plan §12)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import RiskLevel, Route


class ResearchRequest(BaseModel):
    """Raw user request captured at intake, before any interpretation."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    objective: str
    decision_context: str | None = None
    audience: str | None = None
    submitted_at: datetime | None = None
    attachments: list[str] = Field(default_factory=list)
    requested_route: Route | None = None
    user_constraints: dict[str, Any] = Field(default_factory=dict)


class ResearchContract(BaseModel):
    """The materialized agreement that constrains all downstream agents (§12).

    The contract exists so that no agent can reinterpret the objective in an
    incompatible way. Every field is either filled by intake or defaulted to a
    safe, explicit value — nothing is silently left open.
    """

    model_config = ConfigDict(extra="forbid")

    contract_id: str
    objective: str
    decision_context: str | None = None
    audience: str | None = None
    scope: str | None = None
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    time_window: dict[str, str] = Field(default_factory=dict)
    geography: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    source_policy: str | None = None
    required_primary_sources: list[str] = Field(default_factory=list)
    prohibited_sources: list[str] = Field(default_factory=list)
    freshness: dict[str, str] = Field(default_factory=dict)
    output_format: str = "markdown"
    risk_level: RiskLevel = RiskLevel.MEDIUM
    route: Route = Route.FOCUSED_DEEP_RESEARCH
    budget: dict[str, Any] = Field(default_factory=dict)
    human_checkpoints: list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)

    def languages_are_explicit(self) -> bool:
        return bool(self.languages)
