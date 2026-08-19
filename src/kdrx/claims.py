"""Claim-evidence graph logic (plan §22, §23, §24).

Atomic decomposition, the transparent standing function, calibration and
independence accounting. Standing is never "the average of agent opinions";
it is a deterministic function of direct support, source quality,
independence, scope match, recency, contradiction strength, methodological
consistency and extraction confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kdrx.schemas.claims import Claim, ClaimEvidenceEdge
from kdrx.schemas.enums import EdgeDirectness, Standing

#: Conjunction boundaries for naive compound-sentence splitting.
_SPLIT_RE = re.compile(
    r"\s+(?:and|&)\s+|\s+(?:while|whereas)\s+|\s*;\s*|\s+\.\s+",
    re.IGNORECASE,
)


def split_compound_statement(statement: str) -> list[str]:
    """Deterministic heuristic decomposition of a compound statement.

    This is a *fallback* for the claim decomposer agent: it splits on
    conjunctions and sentence boundaries so a sentence like ``"A increased
    accuracy and reduced cost in three datasets"`` yields its atomic parts.
    Full semantic decomposition (which datasets, which populations) is
    model-assisted and layered on top.
    """
    parts = [p.strip(" .") for p in _SPLIT_RE.split(statement) if p.strip(" .")]
    return parts or [statement.strip()]


def decompose_into_claims(claim_id: str, statement: str) -> list[Claim]:
    """Produce atomic claims from a (possibly compound) statement (plan §22)."""
    parts = split_compound_statement(statement)
    return [
        Claim(claim_id=f"{claim_id}-{i + 1}", statement=p) for i, p in enumerate(parts)
    ]


# --------------------------------------------------------------------------- #
# Standing
# --------------------------------------------------------------------------- #
@dataclass
class StandingResult:
    claim_id: str
    standing: Standing
    confidence: float
    components: dict[str, float] = field(default_factory=dict)
    calibration_basis: str = ""

    def as_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "standing": self.standing.value,
            "confidence": round(self.confidence, 4),
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "calibration_basis": self.calibration_basis,
        }


_WEIGHTS: dict[str, float] = {
    "direct_support": 0.20,
    "source_independence": 0.20,
    "independent_sources": 0.15,
    "source_quality": 0.10,
    "scope_match": 0.10,
    "methodological_consistency": 0.10,
    "extraction_confidence": 0.10,
    "recency": 0.05,
}


def compute_standing(
    claim: Claim,
    support_edges: list[ClaimEvidenceEdge],
    contradict_edges: list[ClaimEvidenceEdge],
    *,
    evidence_source: dict[str, str] | None = None,
    source_family: dict[str, str] | None = None,
    recency: float = 0.5,
    methodological_consistency: float = 0.5,
) -> StandingResult:
    """Transparent standing function (plan §24).

    ``evidence_source`` maps evidence_id -> source_id; ``source_family`` maps
    source_id -> family representative (see
    :func:`kdrx.corpus.independence_families`). Two sources in the same family
    count once, not twice.
    """
    evidence_source = evidence_source or {}
    source_family = source_family or {}

    def source_of(edge: ClaimEvidenceEdge) -> str:
        return evidence_source.get(edge.evidence_id, edge.evidence_id)

    def family_of(source_id: str) -> str:
        return source_family.get(source_id, source_id)

    support = [e for e in support_edges if e.is_supportive()]
    contradicts = [e for e in contradict_edges if e.is_contradicting()]

    supporting_sources = {source_of(e) for e in support}
    independent_families = {family_of(s) for s in supporting_sources}

    components: dict[str, float] = {}
    if support:
        components["direct_support"] = sum(
            1.0 for e in support if e.directness == EdgeDirectness.DIRECT
        ) / len(support)
        components["source_quality"] = sum(e.source_quality for e in support) / len(
            support
        )
        components["source_independence"] = sum(e.independence for e in support) / len(
            support
        )
        components["scope_match"] = sum(1.0 for e in support if e.scope_match) / len(
            support
        )
        components["extraction_confidence"] = sum(e.confidence for e in support) / len(
            support
        )
    else:
        components["direct_support"] = 0.0
        components["source_quality"] = 0.0
        components["source_independence"] = 0.0
        components["scope_match"] = 0.0
        components["extraction_confidence"] = 0.0

    # Capped credit: 3 independent families is "fully corroborated".
    components["independent_sources"] = min(len(independent_families) / 3.0, 1.0)
    components["recency"] = max(0.0, min(1.0, recency))
    components["methodological_consistency"] = max(
        0.0, min(1.0, methodological_consistency)
    )
    # Contradiction penalty applied outside the weighted sum.
    contradiction_strength = min(len(contradicts) / 3.0, 1.0)
    components["contradiction_strength"] = contradiction_strength

    score = sum(_WEIGHTS[k] * components.get(k, 0.0) for k in _WEIGHTS)
    score = score * (1.0 - contradiction_strength)

    if not support and contradicts:
        standing = Standing.CONTRADICTED
    elif contradiction_strength >= 2 / 3 and not support:
        standing = Standing.CONTRADICTED
    elif score >= 0.7 and len(independent_families) >= 2:
        standing = Standing.SUPPORTED
    elif score >= 0.5:
        standing = Standing.MIXED
    elif score >= 0.3:
        standing = Standing.WEAK
    else:
        standing = Standing.UNRESOLVED

    basis = (
        f"support={len(support)} contradict={len(contradicts)} "
        f"families={len(independent_families)} score={score:.3f}"
    )

    return StandingResult(
        claim_id=claim.claim_id,
        standing=standing,
        confidence=max(0.0, min(1.0, score)),
        components=components,
        calibration_basis=basis,
    )


# --------------------------------------------------------------------------- #
# Independence
# --------------------------------------------------------------------------- #
def invert_families(families: dict[str, list[str]]) -> dict[str, str]:
    """Invert ``{family_id: [source_ids]}`` to ``{source_id: family_id}``."""
    out: dict[str, str] = {}
    for family_id, members in families.items():
        for member in members:
            out[member] = family_id
    return out


def independent_support_count(
    support_edges: list[ClaimEvidenceEdge],
    *,
    evidence_source: dict[str, str] | None = None,
    source_family: dict[str, str] | None = None,
) -> int:
    """Number of *independent* source families backing a set of support edges.

    Five news articles syndicating one press release count as one family.
    """
    evidence_source = evidence_source or {}
    source_family = source_family or {}
    families = set()
    for e in support_edges:
        if not e.is_supportive():
            continue
        source = evidence_source.get(e.evidence_id, e.evidence_id)
        families.add(source_family.get(source, source))
    return len(families)


# --------------------------------------------------------------------------- #
# Coverage
# --------------------------------------------------------------------------- #
def claim_coverage(
    claims: list[Claim], resolved_standing: set[Standing]
) -> tuple[float, list[str]]:
    """Fraction of claims with a resolved standing and the unresolved ids.

    ``resolved_standing`` is the set of standings that count as "no longer open"
    (typically SUPPORTED, MIXED, WEAK, CONTRADICTED — everything but
    UNRESOLVED).
    """
    total = len(claims)
    if total == 0:
        return 1.0, []
    unresolved = [c.claim_id for c in claims if c.standing not in resolved_standing]
    covered = total - len(unresolved)
    return covered / total, unresolved
