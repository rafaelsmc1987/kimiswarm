"""KDR-X: research kernel with traceable local evidence.

The package provides a persistent plan, dependency-ready scheduler, source
snapshots and deterministic integrity checks. Claude Code and Codex adapters
are available for explicitly configured inference. Semantic verification and
live host/comparative acceptance remain incomplete; see docs/EXECUTION.md.
"""

__version__ = "0.3.0"

from kdrx.schemas import (  # noqa: F401  (re-exported for ergonomic imports)
    AgentBrief,
    AgentResult,
    ArtifactRecord,
    Claim,
    ClaimEvidenceEdge,
    ContradictionCluster,
    DeliveryManifest,
    EvidenceSpan,
    GateDecision,
    ResearchContract,
    ResearchPlan,
    ResearchRequest,
    RunManifest,
    SourceRecord,
    TaskSpec,
)

__all__ = [
    "AgentBrief",
    "AgentResult",
    "ArtifactRecord",
    "Claim",
    "ClaimEvidenceEdge",
    "ContradictionCluster",
    "DeliveryManifest",
    "EvidenceSpan",
    "GateDecision",
    "ResearchContract",
    "ResearchPlan",
    "ResearchRequest",
    "RunManifest",
    "SourceRecord",
    "TaskSpec",
    "__version__",
]
