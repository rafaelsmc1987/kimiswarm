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
from typing import Any

from kdrx.corpus import tokenize
from kdrx.schemas.claims import Claim, ClaimEvidenceEdge
from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
from kdrx.schemas.enums import (
    EdgeDirectness,
    EdgeRelation,
    ExtractionStatus,
    QualityGrade,
    Standing,
)

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


# --------------------------------------------------------------------------- #
# Structured decomposition (T-07-01)
# --------------------------------------------------------------------------- #
_ASSERTION_RE = re.compile(
    r"\b(is|are|was|were|has|have|had|shows?|demonstrates?|causes?|"
    r"increases?|decreases?|reduces?|improves?|outperforms?|fails?|"
    r"costs?|requires?|supports?|claims?|reports?)\b",
    re.IGNORECASE,
)

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_POPULATION_RE = re.compile(
    r"\b(children|adults|patients|students|users|developers|models|datasets|"
    r"benchmarks|enterprises|households)\b",
    re.IGNORECASE,
)
_JURISDICTION_RE = re.compile(
    r"\b(us|usa|uk|eu|europe|brazil|china|japan|india|germany|france)\b",
    re.IGNORECASE,
)


def is_falsifiable(sentence: str) -> bool:
    """Whether a sentence carries a verifiable assertion signal (T-07-01).

    O decomposer antigo elevava QUALQUER sentence com número a claim; agora a
    sentence precisa de um predicado verificável (verbo de asserção/medição) —
    um número solto sem predicado não é claim.
    """
    return bool(sentence.strip()) and bool(_ASSERTION_RE.search(sentence))


def extract_scope(statement: str) -> dict[str, Any]:
    """Extract scope constraints (time/population/jurisdiction) deterministically."""
    scope: dict[str, Any] = {}
    years = _YEAR_RE.findall(statement)
    if years:
        scope["time"] = years[0] if len(years) == 1 else f"{min(years)}-{max(years)}"
    m = _POPULATION_RE.search(statement)
    if m:
        scope["population"] = m.group(1).lower()
    m = _JURISDICTION_RE.search(statement)
    if m:
        scope["jurisdiction"] = m.group(1).lower()
    return scope


def decompose_into_claims(claim_id: str, statement: str) -> list[Claim]:
    """Produce atomic claims from a (possibly compound) statement (plan §22).

    T-07-01: ids estáveis — statement atômico mantém o id-base; só compostos
    ganham sufixo. Scope heurístico preenche claim.scope para os checks de
    scope/temporal match (T-07-03).
    """
    parts = split_compound_statement(statement)
    if len(parts) == 1:
        return [
            Claim(claim_id=claim_id, statement=parts[0], scope=extract_scope(parts[0]))
        ]
    return [
        Claim(claim_id=f"{claim_id}-{i + 1}", statement=p, scope=extract_scope(p))
        for i, p in enumerate(parts)
    ]


# --------------------------------------------------------------------------- #
# Independent entailment verification (T-07-02)
# --------------------------------------------------------------------------- #
_NUM_TOK_RE = re.compile(r"\d+(?:\.\d+)?%?")


def lexical_coverage(statement: str, span_text: str) -> float:
    """Fração dos tokens da claim presentes no texto (overlap de sujeito)."""
    claim_tokens = tokenize(statement)
    if not claim_tokens:
        return 0.0
    span_tokens = set(tokenize(span_text))
    return sum(1 for t in claim_tokens if t in span_tokens) / len(claim_tokens)


def entailment_score(statement: str, span_text: str) -> float:
    """Lexical entailment proxy between a claim and an evidence span.

    70% cobertura lexical, 30% consistência numérica (quando a claim carrega
    números): um span que cobre o sujeito mas diverge/falta o número cai na
    faixa de suporte parcial (0.4..0.8) — detectável sem LLM.
    """
    coverage = lexical_coverage(statement, span_text)
    if not tokenize(statement):
        return 0.0
    claim_nums = _NUM_TOK_RE.findall(statement)
    if claim_nums:
        span_nums = set(_NUM_TOK_RE.findall(span_text))
        num_score = sum(1 for n in claim_nums if n in span_nums) / len(claim_nums)
        return 0.7 * coverage + 0.3 * num_score
    return coverage


def numeric_disagreement(statement: str, other_text: str) -> bool:
    """Same-subject numeric disagreement proxy (claim numbers absent + other's present)."""
    claim_nums = _NUM_TOK_RE.findall(statement)
    other_nums = set(_NUM_TOK_RE.findall(other_text))
    return bool(claim_nums) and bool(other_nums) and not any(
        n in other_nums for n in claim_nums
    )


# --------------------------------------------------------------------------- #
# Edge relations (T-07-03)
# --------------------------------------------------------------------------- #
def compute_scope_match(claim: Claim, span_text: str) -> bool:
    """Scope constraints (time/population/jurisdiction) must echo in the span."""
    lowered = span_text.lower()
    for _key, value in (claim.scope or {}).items():
        if value is None:
            continue
        if str(value).lower() not in lowered:
            return False
    return True


def compute_temporal_match(claim: Claim, source_date: Any | None) -> bool:
    """Claim time scope must agree with the source's publication year."""
    time_scope = (claim.scope or {}).get("time")
    if not time_scope or source_date is None:
        return True
    year = getattr(source_date, "year", None)
    if year is None:
        return True
    return str(year) in str(time_scope)


def classify_edge_relation(
    claim: Claim,
    span_text: str,
    *,
    entailment: float,
    scope_match: bool,
    temporal_match: bool,
) -> EdgeRelation:
    """Map entailment + match signals to the full EdgeRelation vocabulary.

    CONTRADICTS exige overlap de sujeito ALTO (senão uma janela curta seria
    mis-lida como contradição); scope/time mismatch em suporte cheio vira
    QUALIFIES — a evidência apoia com qualificação de escopo.
    """
    if numeric_disagreement(claim.statement, span_text) and lexical_coverage(
        claim.statement, span_text
    ) >= 0.6:
        return EdgeRelation.CONTRADICTS
    if entailment >= 0.8:
        if not scope_match or not temporal_match:
            return EdgeRelation.QUALIFIES
        return EdgeRelation.SUPPORTS
    if entailment >= 0.4:
        return EdgeRelation.PARTIALLY_SUPPORTS
    if entailment >= 0.15:
        return EdgeRelation.CONTEXT_ONLY
    return EdgeRelation.IRRELEVANT


# --------------------------------------------------------------------------- #
# Derived edge construction (T-07-06) — scores NUNCA constantes
# --------------------------------------------------------------------------- #
_QUALITY_NUMERIC: dict[QualityGrade, float] = {
    QualityGrade.EXCELLENT: 1.0,
    QualityGrade.GOOD: 0.8,
    QualityGrade.ADEQUATE: 0.6,
    QualityGrade.WEAK: 0.3,
    QualityGrade.UNVERIFIED: 0.4,
    QualityGrade.REJECTED: 0.0,
}


def source_quality_score(source: SourceRecord | None) -> float:
    """Quality score DERIVED from source attributes (grade + identity signals)."""
    if source is None:
        return 0.2
    score = _QUALITY_NUMERIC[source.quality_grade]
    if source.content_hash:
        score += 0.1  # identidade de conteúdo verificável
    if source.date is not None:
        score += 0.05  # databilidade conhecida
    return min(score, 1.0)


def derive_edge(
    claim: Claim,
    span: EvidenceSpan,
    *,
    source: SourceRecord | None,
    family_size: int = 1,
) -> ClaimEvidenceEdge:
    """Build a ClaimEvidenceEdge with every score DERIVED from inputs (T-07-06).

    Nenhuma constante: entailment do verificador independente (T-07-02),
    relation do classificador (T-07-03), quality dos atributos da fonte,
    independence do tamanho da família de syndication, confidence do status
    de extração. A base de derivação vai em ``limitations`` (auditável).
    """
    ent = entailment_score(claim.statement, span.verbatim_span)
    scope_match = compute_scope_match(claim, span.verbatim_span)
    temporal_match = compute_temporal_match(claim, source.date if source else None)
    relation = classify_edge_relation(
        claim,
        span.verbatim_span,
        entailment=ent,
        scope_match=scope_match,
        temporal_match=temporal_match,
    )
    quality = source_quality_score(source)
    independence = 1.0 / max(1, family_size)
    extracted = source is not None and source.extraction_status == ExtractionStatus.EXTRACTED
    confidence = 1.0 if extracted and span.has_exact_span() else 0.5
    return ClaimEvidenceEdge(
        edge_id=f"E-{claim.claim_id}-{span.evidence_id}",
        claim_id=claim.claim_id,
        evidence_id=span.evidence_id,
        relation=relation,
        directness=EdgeDirectness.DIRECT,
        entailment=ent,
        source_quality=quality,
        independence=independence,
        scope_match=scope_match,
        temporal_match=temporal_match,
        verifier="deterministic-entailment-v1",
        confidence=confidence,
        limitations=[
            f"derived: entailment={ent:.2f} quality={quality:.2f} "
            f"independence=1/{max(1, family_size)} extraction={extracted}"
        ],
    )


# --------------------------------------------------------------------------- #
# Automatic contradiction discovery (T-07-04) & falsification swarm (T-07-05)
# --------------------------------------------------------------------------- #
_NEG_RE = re.compile(r"\b(?:not|no|never|n't)\b")


_NEG_STRIP_RE = re.compile(r"\b(?:not|no|never|n't|do|does|did)\b")


def _naive_stem(token: str) -> str:
    """Plural/3a-pessoa determinístico: 'improves'->'improve', 'nodes'->'node'."""
    return token[:-1] if token.endswith("s") and len(token) > 3 else token


def _negation_normalized(statement: str) -> tuple[str, bool]:
    """(subject sem números/negações/auxiliares, is_negated) para pairing."""
    negated = bool(_NEG_RE.search(statement.lower()))
    subject = _NUM_TOK_RE.sub("<NUM>", statement)
    subject = _NEG_STRIP_RE.sub(" ", subject.lower())
    subject = re.sub(r"\s+", " ", subject).strip()
    subject = " ".join(_naive_stem(t) for t in subject.split())
    return subject, negated


def discover_contradiction_pairs(claims: list[Claim]) -> list[tuple[str, str]]:
    """Find contradicting claim pairs WITHOUT provided pairs (T-07-04).

    Dois detectores determinísticos: (a) mesmo sujeito normalizado com números
    divergentes; (b) mesmo sujeito com polaridade de negação oposta.
    """
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(claims):
        subj_a, neg_a = _negation_normalized(a.statement)
        nums_a = set(_NUM_TOK_RE.findall(a.statement))
        for b in claims[i + 1 :]:
            subj_b, neg_b = _negation_normalized(b.statement)
            if subj_a != subj_b:
                continue
            nums_b = set(_NUM_TOK_RE.findall(b.statement))
            numeric = bool(nums_a and nums_b and nums_a != nums_b)
            polarity = neg_a != neg_b
            if numeric or polarity:
                pairs.append((a.claim_id, b.claim_id))
    return pairs


@dataclass
class CounterevidenceHit:
    """One counterevidence search hit against a claim (T-07-05)."""

    claim_id: str
    doc_id: str
    reason: str
    score: float


def search_counterevidence(
    claim: Claim, corpus: Any, *, top_k: int = 3, own_source_id: str | None = None
) -> list[CounterevidenceHit]:
    """Execute the falsification swarm's searches against the corpus.

    O swarm (verification.FalsificationPlan) define os papéis; esta é a busca
    ATIVA de counterevidence: query = statement da claim; hit = doc rankeado
    cujo texto diverge da claim (número ou polaridade) — a própria fonte do
    claim é excluída (self-evidence não é refutação).
    """
    hits: list[CounterevidenceHit] = []
    claim_neg_subject, claim_neg = _negation_normalized(claim.statement)
    for doc, score in corpus.search(claim.statement, top_k=top_k * 3):
        if own_source_id is not None and doc.doc_id == own_source_id:
            continue
        if numeric_disagreement(claim.statement, doc.text):
            hits.append(
                CounterevidenceHit(claim.claim_id, doc.doc_id, "numeric_disagreement", score)
            )
            continue
        doc_subject, doc_neg = _negation_normalized(doc.text)
        if claim_neg_subject == doc_subject and claim_neg != doc_neg:
            hits.append(CounterevidenceHit(claim.claim_id, doc.doc_id, "polarity_flip", score))
        if len(hits) >= top_k:
            break
    return hits[:top_k]


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
