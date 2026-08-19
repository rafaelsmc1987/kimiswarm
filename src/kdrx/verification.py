"""Source trust, prompt-injection boundary, contradiction and falsification.

This module is the deterministic part of the epistemic core:

- source identity / retraction / COI / currency checks (plan §20);
- the instruction/data boundary: retrieved content is *untrusted data* (§32);
- a contradiction clusterer and type detector (§25);
- the falsification-swarm plan for critical claims (§26).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kdrx.schemas.claims import Claim, ContradictionCluster
from kdrx.schemas.corpus import SourceRecord
from kdrx.schemas.enums import (
    ContradictionStatus,
    ContradictionType,
    EdgeRelation,
    QualityGrade,
    RetractionStatus,
    SourceType,
)
from kdrx.schemas.gate import GateCheck, GateDecision
from kdrx.schemas.gate import GateKind


# --------------------------------------------------------------------------- #
# Prompt-injection / instruction-data boundary (plan §32)
# --------------------------------------------------------------------------- #
_INJECTION_MARKERS: tuple[str, ...] = (
    "ignore all previous instructions",
    "ignore the above",
    "ignore prior instructions",
    "disregard your",
    "disregard previous",
    "you are now",
    "your new instructions",
    "system prompt",
    "do not follow your",
    "forget your instructions",
    "reveal your instructions",
    "act as if",
    "this is a new directive",
    "override your",
    "i am your",
    "as an ai you must",
    "you must respond only",
)

#: Domain-style egress / instruction strings that try to change the workflow.
_WORKFLOW_TAMPER: tuple[str, ...] = (
    "set your objective",
    "change your task",
    "ignore your rubric",
    "bypass your",
    "you no longer have to",
    "output path is now",
    "disable your",
)


@dataclass
class InjectionScan:
    """Result of scanning untrusted retrieved text."""

    text: str
    markers: list[str] = field(default_factory=list)
    score: int = 0

    @property
    def suspicious(self) -> bool:
        return self.score >= 2

    @property
    def critical(self) -> bool:
        return self.score >= 4


def scan_prompt_injection(text: str) -> InjectionScan:
    """Detect imperative strings in retrieved content.

    Conservative and marker-based on purpose: retrieved pages, PDFs, issues and
    comments are *data*, never instructions. Any hit is flagged for the
    prompt-injection auditor; the workflow, rubric, permissions and gates are
    never mutated from this content.
    """
    lowered = text.lower()
    markers = [
        m for m in _INJECTION_MARKERS + _WORKFLOW_TAMPER if m in lowered
    ]
    score = sum(2 if m in _WORKFLOW_TAMPER else 1 for m in markers)
    return InjectionScan(text=text, markers=markers, score=score)


def content_is_untrusted(text: str) -> bool:
    """True when content carries any imperative marker (data, not instruction)."""
    return scan_prompt_injection(text).suspicious


# --------------------------------------------------------------------------- #
# Source trust (plan §20)
# --------------------------------------------------------------------------- #
def source_identity_checks(record: SourceRecord) -> list[GateCheck]:
    """Existence / identity-match checks that are computable locally."""
    checks: list[GateCheck] = []
    has_uri = bool(record.canonical_uri.strip())
    checks.append(
        GateCheck(check_id="URI", description="canonical URI present", passed=has_uri)
    )
    checks.append(
        GateCheck(check_id="TITLE", description="title present", passed=bool(record.title.strip()))
    )
    checks.append(
        GateCheck(
            check_id="TYPE",
            description="source type is not UNKNOWN",
            passed=record.source_type is not SourceType.UNKNOWN,
        )
    )
    checks.append(
        GateCheck(
            check_id="HASH",
            description="content hash present (enables dedup & versioning)",
            passed=bool(record.content_hash),
        )
    )
    return checks


def retraction_check(record: SourceRecord) -> GateCheck:
    """Flag retracted/corrected sources so they never ground a material claim."""
    ok = record.retraction_status in (RetractionStatus.NONE, RetractionStatus.CORRECTED)
    return GateCheck(
        check_id="RETRACTION",
        description=f"retraction status acceptable ({record.retraction_status})",
        passed=ok,
        details=record.retraction_status,
    )


def currency_check(record: SourceRecord, max_age_days: int = 730) -> GateCheck:
    """Staleness flag; a source can be real yet out-of-date (plan §20)."""
    from datetime import datetime, timezone

    if record.date is None:
        return GateCheck(
            check_id="CURRENCY",
            description="source date unknown; cannot assert freshness",
            passed=False,
        )
    now = datetime.now(timezone.utc)
    age_days = (now - record.date).days if record.date.tzinfo else (now.replace(tzinfo=None) - record.date).days
    passed = age_days <= max_age_days
    return GateCheck(
        check_id="CURRENCY",
        description=f"source age {age_days}d within {max_age_days}d",
        passed=passed,
        details={"age_days": age_days, "max_age_days": max_age_days},
    )


def coi_check(record: SourceRecord) -> GateCheck:
    passed = not record.conflicts_of_interest
    return GateCheck(
        check_id="COI",
        description="no declared conflicts of interest",
        passed=passed,
        details=record.conflicts_of_interest,
    )


def source_quality_policy(record: SourceRecord) -> QualityGrade:
    """A small domain-relative trust heuristic (plan §20).

    The full registry is domain-specific; this default combines the signals a
    local record carries. It is a *floor*, never a replacement for verification.
    """
    grade = QualityGrade.UNVERIFIED
    if record.retraction_status == RetractionStatus.RETRACTED:
        return QualityGrade.REJECTED
    if record.primary_or_secondary.value == "primary":
        grade = QualityGrade.GOOD
    elif record.quality_grade is not QualityGrade.UNVERIFIED:
        grade = record.quality_grade
    if record.conflicts_of_interest:
        grade = QualityGrade.WEAK
    return grade


def source_trust_gate(record: SourceRecord) -> GateDecision:
    """Compose the identity + retraction + COI + currency checks into a gate."""
    checks = source_identity_checks(record) + [
        retraction_check(record),
        coi_check(record),
    ]
    return GateDecision.compose(
        gate_id=f"gate:source:{record.source_id}",
        kind=GateKind.SOURCE,
        checks=checks,
        warn_is_pass=True,
    )


# --------------------------------------------------------------------------- #
# Contradiction detection & clustering (plan §25)
# --------------------------------------------------------------------------- #
def detect_contradiction_type(a: Claim, b: Claim) -> ContradictionType:
    """Heuristically classify the *kind* of disagreement between two claims.

    Semantic contradiction detection is model-assisted; this deterministic
    classifier covers the well-defined structural cases and defaults to
    ``FACTUAL`` otherwise.
    """
    if a.claim_type.value in ("forecast", "normative") or b.claim_type.value in (
        "forecast",
        "normative",
    ):
        return ContradictionType.FACTUAL
    a_scope = a.scope or {}
    b_scope = b.scope or {}
    # temporal mismatch: disjoint explicit time windows
    if "time" in a_scope and "time" in b_scope and a_scope["time"] != b_scope["time"]:
        return ContradictionType.TEMPORAL
    # jurisdiction mismatch
    if "jurisdiction" in a_scope and "jurisdiction" in b_scope and a_scope["jurisdiction"] != b_scope["jurisdiction"]:
        return ContradictionType.JURISDICTION
    # population/sample mismatch
    if ("population" in a_scope and "population" in b_scope and a_scope["population"] != b_scope["population"]):
        return ContradictionType.POPULATION_SAMPLE
    # numerical disagreement on same subject
    a_num = _extract_numbers(a.statement)
    b_num = _extract_numbers(b.statement)
    if a_num and b_num and a_num != b_num:
        return ContradictionType.NUMERICAL
    return ContradictionType.FACTUAL


def _extract_numbers(statement: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?%?", statement)


def cluster_contradictions(
    claims: list[Claim], contradicting_pairs: list[tuple[str, str]]
) -> list[ContradictionCluster]:
    """Group claims connected by CONTRADICTS edges into clusters.

    Uses union-find so a 3-way disagreement (A vs B, B vs C) becomes one cluster.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for x, y in contradicting_pairs:
        union(x, y)

    groups: dict[str, list[str]] = {}
    for c in claims:
        groups.setdefault(find(c.claim_id), []).append(c.claim_id)

    clusters: list[ContradictionCluster] = []
    for i, members in enumerate(groups.values()):
        if len(members) < 2:
            continue
        member_claims = [c for c in claims if c.claim_id in members]
        ctype = (
            detect_contradiction_type(member_claims[0], member_claims[1])
            if len(member_claims) >= 2
            else ContradictionType.FACTUAL
        )
        clusters.append(
            ContradictionCluster(
                contradiction_id=f"CT-{i}",
                claims=members,
                contradiction_type=ctype,
                status=ContradictionStatus.OPEN,
            )
        )
    return clusters


# --------------------------------------------------------------------------- #
# Falsification swarm (plan §26)
# --------------------------------------------------------------------------- #
@dataclass
class FalsificationPlan:
    claim_id: str
    roles: list[dict] = field(default_factory=list)
    minimum_new_searches: int = 3

    @classmethod
    def for_claim(cls, claim: Claim) -> "FalsificationPlan":
        """The five falsification roles for a critical claim."""
        roles = [
            {"role": "support", "goal": "find support", "query_hint": claim.statement},
            {"role": "refute", "goal": "find refutation", "query_hint": f"contradiction to: {claim.statement}"},
            {"role": "alternative", "goal": "find alternative explanations", "query_hint": f"alternative to: {claim.statement}"},
            {"role": "verify", "goal": "verify evidence spans", "query_hint": None},
            {"role": "calibrate", "goal": "update standing", "query_hint": None},
        ]
        return cls(claim_id=claim.claim_id, roles=roles)


def minimum_new_search_rule(used_queries: set[str], new_queries: list[str], minimum: int = 3) -> bool:
    """Enforce that conflict resolution uses fresh, unused queries (plan §26)."""
    fresh = [q for q in new_queries if q not in used_queries]
    return len(fresh) >= minimum
