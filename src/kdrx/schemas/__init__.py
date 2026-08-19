"""Canonical KDR-X schemas.

Re-exported flat so ``from kdrx.schemas import Claim`` works and so the
``SCHEMAS`` registry below can drive JSON-Schema export (plan §41).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact import ArtifactRecord, DeliveryManifest
from .claims import (
    Claim,
    ClaimEvidenceEdge,
    ContradictionCluster,
    FalsificationCriteria,
)
from .corpus import EvidenceSpan, Locator, SourceRecord
from .gate import GateCheck, GateDecision
from .plan import (
    AcceptanceCriteria,
    AgentBrief,
    AgentResult,
    Budget,
    OwnershipEntry,
    ResearchPlan,
    RetryPolicy,
    RunManifest,
    TaskSpec,
)
from .request import ResearchContract, ResearchRequest

__all__ = [
    "AcceptanceCriteria",
    "AgentBrief",
    "AgentResult",
    "ArtifactRecord",
    "Budget",
    "Claim",
    "ClaimEvidenceEdge",
    "ContradictionCluster",
    "DeliveryManifest",
    "EvidenceSpan",
    "FalsificationCriteria",
    "GateCheck",
    "GateDecision",
    "Locator",
    "OwnershipEntry",
    "ResearchContract",
    "ResearchPlan",
    "ResearchRequest",
    "RetryPolicy",
    "RunManifest",
    "SourceRecord",
    "TaskSpec",
]

#: The 15 canonical schemas (plan §41) in priority order.
SCHEMAS: dict[str, type] = {
    "ResearchRequest": ResearchRequest,
    "ResearchContract": ResearchContract,
    "ResearchPlan": ResearchPlan,
    "TaskSpec": TaskSpec,
    "AgentBrief": AgentBrief,
    "AgentResult": AgentResult,
    "SourceRecord": SourceRecord,
    "EvidenceSpan": EvidenceSpan,
    "Claim": Claim,
    "ClaimEvidenceEdge": ClaimEvidenceEdge,
    "ContradictionCluster": ContradictionCluster,
    "GateDecision": GateDecision,
    "ArtifactRecord": ArtifactRecord,
    "RunManifest": RunManifest,
    "DeliveryManifest": DeliveryManifest,
}


def export_json_schemas(out_dir: str | Path) -> dict[str, Path]:
    """Write each canonical schema as ``<Name>.schema.json``.

    Returns a mapping of schema name to the written file path.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, model in SCHEMAS.items():
        path = out / f"{name}.schema.json"
        schema: dict[str, Any] = model.model_json_schema()
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        written[name] = path
    return written
