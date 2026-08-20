"""KDR-X — KimiSwarm Deep Research eXtended.

A claim-evidence operating system for state-of-the-art deep research. The
package ships a deterministic control plane (research contract -> DAG -> wave
scheduler -> gates) plus the epistemic primitives (source trust, atomic claims,
evidence spans, contradiction/falsification, calibrated standing) described in
``Plano/PLANO_SOTA_SUPER_DEEP_RESEARCH.md``.

Layers (see plan §10):

1.  Control Plane
2.  Research Contract
3.  Retrieval & Corpus
4.  Source Trust
5.  Claim-Evidence Graph
6.  Falsification & Contradiction
7.  Analytical Compute
8.  Calibrated Synthesis
9.  Review & Integrity
10. Persistent Research Artifact
"""

__version__ = "0.2.0"

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
