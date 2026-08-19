"""Persistent research artifact and delivery manifest (plan §31, §41)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import ArtifactKind, SealLevel


class ArtifactRecord(BaseModel):
    """One persisted artifact with provenance and a seal."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    kind: ArtifactKind
    path: str
    content_hash: str
    seal_level: SealLevel = SealLevel.LEVEL_1_HASHED
    produced_by: str | None = None
    produced_at: datetime | None = None
    inputs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryManifest(BaseModel):
    """What a run actually delivers (plan §31)."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str
    run_id: str
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    final_integrity_pass: bool = False
    secret_scan_clean: bool = False
    artifact_open_test_passed: bool = False
    unresolved_critical_claims: list[str] = Field(default_factory=list)
    delivered_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_complete(self) -> bool:
        return bool(
            self.final_integrity_pass
            and self.secret_scan_clean
            and self.artifact_open_test_passed
            and self.artifacts
        )
