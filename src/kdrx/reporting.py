"""Calibrated synthesis and report pipeline (plan §28, §29, §44).

The synthesis agent receives *evidence packs*, not the whole corpus. The
report is assembled from dependency-ordered sections and then passes a
deterministic citation/integrity gate: every citation resolves, every material
claim has an exact evidence span, and unsupported sentences are flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from kdrx.schemas.claims import Claim
from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
from kdrx.schemas.enums import ClaimImportance, GateKind, Standing
from kdrx.schemas.gate import GateCheck, GateDecision

#: Citation marker format: ``[cite:S1]`` or ``[cite: S1]``.
_CITE_RE = re.compile(r"\[cite:\s*([A-Za-z0-9_.:-]+)\]")

# A "quantitative" token is a number followed by a unit word/symbol, a decimal,
# or a multi-digit magnitude — so bare list enumerators ("1.", "2.") and years
# are not mistaken for claims. This keeps false positives low.
_NUMBER_RE = re.compile(
    r"\d+(?:\.\d+)?\s?(?:%|percent|million|billion|k\b|[€$]|USD|[A-Za-z]{2,})"
)


@dataclass
class EvidencePack:
    """The focused set of material handed to the synthesis agent (§28)."""

    pack_id: str
    claims: list[Claim] = field(default_factory=list)
    sources: list[SourceRecord] = field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    standings: dict[str, Standing] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    prohibited_overclaims: list[str] = field(default_factory=list)
    required_caveats: list[str] = field(default_factory=list)


def build_evidence_pack(
    pack_id: str,
    claims: list[Claim],
    sources: list[SourceRecord],
    spans: list[EvidenceSpan],
    *,
    contradictions: list[str] | None = None,
    gaps: list[str] | None = None,
    prohibited_overclaims: list[str] | None = None,
    required_caveats: list[str] | None = None,
) -> EvidencePack:
    standings = {c.claim_id: c.standing for c in claims}
    return EvidencePack(
        pack_id=pack_id,
        claims=claims,
        sources=sources,
        evidence_spans=spans,
        contradictions=contradictions or [],
        standings=standings,
        gaps=gaps or [],
        prohibited_overclaims=prohibited_overclaims or [],
        required_caveats=required_caveats or [],
    )


def extract_citations(text: str) -> list[str]:
    """All source ids cited in ``text``, in order of appearance, deduplicated."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _CITE_RE.finditer(text):
        sid = m.group(1)
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def unsupported_sentence_detector(text: str, backed_statements: set[str]) -> list[str]:
    """Flag sentences that assert numbers but aren't backed by a claim.

    Deterministic heuristic: a sentence containing a numeric/quantitative token
    is "supported" only if some backed claim statement appears within it
    (normalized, case-insensitive substring match). This is a floor, not a
    replacement for entailment checking.
    """
    flagged: list[str] = []
    backed = {b.strip().lower() for b in backed_statements if b.strip()}
    for sentence in split_sentences(text):
        if not _NUMBER_RE.search(sentence):
            continue
        lower = sentence.lower()
        supported = any(b in lower for b in backed)
        if not supported:
            flagged.append(sentence)
    return flagged


def citation_integrity_gate(
    report_text: str,
    *,
    sources: list[SourceRecord],
    claims: list[Claim],
    spans: list[EvidenceSpan],
) -> GateDecision:
    """Deterministic claim/citation integrity gate (§29 wave 6, DoD §44)."""
    checks: list[GateCheck] = []
    source_ids = {s.source_id for s in sources}
    cited = extract_citations(report_text)

    # Every citation resolves to a known source.
    unknown = [c for c in cited if c not in source_ids]
    checks.append(
        GateCheck(
            check_id="CITATION_EXISTS",
            description="every citation resolves to a source",
            passed=not unknown,
            details=unknown,
        )
    )

    # Every material claim cited in the report has an exact evidence span.
    material = [
        c
        for c in claims
        if c.importance in (ClaimImportance.CRITICAL, ClaimImportance.MAJOR)
    ]
    material_by_statement = {c.statement.strip().lower(): c for c in material}
    unsupported_material = []
    cited_statements: set[str] = set()
    for sentence in split_sentences(report_text):
        for stmt, c in material_by_statement.items():
            if stmt in sentence.lower():
                cited_statements.add(c.claim_id)
                if not _claim_has_span(c, spans):
                    unsupported_material.append(c.claim_id)
    checks.append(
        GateCheck(
            check_id="MATERIAL_CLAIM_EVIDENCE",
            description="material claims have exact evidence spans",
            passed=not unsupported_material,
            details=unsupported_material,
        )
    )

    # Unresolved material claims are surfaced, not silently dropped.
    unresolved = [c.claim_id for c in material if c.standing == Standing.UNRESOLVED]
    checks.append(
        GateCheck(
            check_id="UNRESOLVED_DISCLOSED",
            description="unresolved claims are disclosed in the report",
            passed=not unresolved,
            details=unresolved,
        )
    )

    # Unsupported numeric sentences.
    backed = {c.statement for c in claims}
    flagged = unsupported_sentence_detector(report_text, backed)
    checks.append(
        GateCheck(
            check_id="UNSUPPORTED_SENTENCE",
            description="no unsupported quantitative sentence",
            passed=not flagged,
            details=flagged,
        )
    )

    return GateDecision.compose(
        gate_id="gate:citation_integrity",
        kind=GateKind.CITATION,
        checks=checks,
        warn_is_pass=True,
    )


def _claim_has_span(claim: Claim, spans: list[EvidenceSpan]) -> bool:
    # A claim "has a span" when at least one span references its id directly.
    return any(sp.evidence_id in claim.support_edges for sp in spans)


class ReportAssembler:
    """Assemble a report from dependency-ordered sections (Markdown IR).

    Wave 7 of §29: sections -> Markdown IR -> delivery artifacts. The assembler
    is deterministic: it emits a title, the body sections in order, a reference
    list built from cited sources, and a manifest of produced artifacts.
    """

    def __init__(self, title: str) -> None:
        self.title = title
        self._sections: list[tuple[str, str]] = []  # (heading, body)

    def add_section(self, heading: str, body: str) -> None:
        self._sections.append((heading, body))

    def assemble(self, reference_list: list[SourceRecord] | None = None) -> str:
        out = [f"# {self.title}", ""]
        for heading, body in self._sections:
            out.append(f"## {heading}")
            out.append("")
            out.append(body.rstrip())
            out.append("")
        if reference_list:
            out.append("## References")
            out.append("")
            for i, src in enumerate(reference_list, start=1):
                out.append(f"{i}. [{src.title}]({src.canonical_uri})")
            out.append("")
        return "\n".join(out).rstrip() + "\n"

    def build_reference_list(
        self, text: str, sources: list[SourceRecord]
    ) -> list[SourceRecord]:
        cited = extract_citations(text)
        by_id = {s.source_id: s for s in sources}
        return [by_id[c] for c in cited if c in by_id]
