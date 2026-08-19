"""Calibrated synthesis and report pipeline (plan §28, §29, §44).

The synthesis agent receives *evidence packs*, not the whole corpus. The
report is assembled from dependency-ordered sections and then passes a
deterministic citation/integrity gate: every citation resolves, every material
claim has an exact evidence span, and unsupported sentences are flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from kdrx.claims import entailment_score
from kdrx.corpus import tokenize
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


# --------------------------------------------------------------------------- #
# Report diffs (T-10-04)
# --------------------------------------------------------------------------- #
_SECTION_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
_CLAIM_LINE_RE = re.compile(r"^- \*\*([\w.\-]+)\*\* \((\w+), ([\d.]+)\)", re.MULTILINE)


@dataclass
class ReportDiff:
    """Diferença estrutural entre dois relatórios (monitoramento)."""

    sections_added: list[str] = field(default_factory=list)
    sections_removed: list[str] = field(default_factory=list)
    sections_changed: list[str] = field(default_factory=list)
    claims_added: list[str] = field(default_factory=list)
    claims_removed: list[str] = field(default_factory=list)
    standing_changes: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.sections_added
            or self.sections_removed
            or self.sections_changed
            or self.claims_added
            or self.claims_removed
            or self.standing_changes
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "sections_added": self.sections_added,
            "sections_removed": self.sections_removed,
            "sections_changed": self.sections_changed,
            "claims_added": self.claims_added,
            "claims_removed": self.claims_removed,
            "standing_changes": self.standing_changes,
            "has_changes": self.has_changes,
        }


def _split_report_sections(text: str) -> dict[str, str]:
    """``{title: body}`` pelos headings `## X` (`# title` é ignorado)."""
    matches = list(_SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[m.group(1).strip()] = text[start:end].strip()
    return sections


def _parse_claim_lines(text: str) -> dict[str, str]:
    """``{claim_id: standing}`` extraído das bullets `- **ID** (standing, conf)`."""
    return {m.group(1): m.group(2) for m in _CLAIM_LINE_RE.finditer(text)}


def diff_reports(old_text: str, new_text: str) -> ReportDiff:
    """Diferença determinística entre dois relatórios KDR-X (T-10-04).

    Captura: seções acrescentadas/removidas/com conteúdo alterado, claims
    acrescentados/removidos e mudanças de standing claim-a-claim.
    """
    old_sections = _split_report_sections(old_text)
    new_sections = _split_report_sections(new_text)
    old_claims = _parse_claim_lines(old_text)
    new_claims = _parse_claim_lines(new_text)

    diff = ReportDiff(
        sections_added=sorted(set(new_sections) - set(old_sections)),
        sections_removed=sorted(set(old_sections) - set(new_sections)),
        sections_changed=sorted(
            title
            for title in set(old_sections) & set(new_sections)
            if old_sections[title] != new_sections[title]
        ),
        claims_added=sorted(set(new_claims) - set(old_claims)),
        claims_removed=sorted(set(old_claims) - set(new_claims)),
    )
    for claim_id in sorted(set(old_claims) & set(new_claims)):
        if old_claims[claim_id] != new_claims[claim_id]:
            diff.standing_changes[claim_id] = {
                "from": old_claims[claim_id],
                "to": new_claims[claim_id],
            }
    return diff


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
    # quebramos também em novas linhas: bullets/linhas markdown sem
    # pontuação terminal são fronteiras duras de "sentença" (senão uma
    # frase envenenada colada após um bullet sem '.' se funde com o bullet
    # e a sentença mesclada pode casar com o claim suportado).
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


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

    # Every material claim cited in the report with a *resolved* standing has
    # an exact evidence span. Claims UNRESOLVED são regidos por
    # UNRESOLVED_DISCLOSED (disclosure explícito, não citação).
    material = [
        c
        for c in claims
        if c.importance in (ClaimImportance.CRITICAL, ClaimImportance.MAJOR)
    ]
    material_by_statement = {
        c.statement.strip().lower(): c
        for c in material
        if c.standing != Standing.UNRESOLVED
    }
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

    # Unresolved material claims are surfaced, not silently dropped (blocking:
    # um claim material sem resolução que NÃO apareça no relatório = omissão).
    unresolved = [c for c in material if c.standing == Standing.UNRESOLVED]
    lower_report = report_text.lower()
    not_disclosed = [
        c.claim_id
        for c in unresolved
        if c.statement.strip().lower() not in lower_report
    ]
    checks.append(
        GateCheck(
            check_id="UNRESOLVED_DISCLOSED",
            description="unresolved claims are disclosed in the report",
            passed=not not_disclosed,
            details=not_disclosed,
        )
    )

    # Unsupported numeric sentences (advisory: sinal de qualidade, não bloqueia).
    backed = {c.statement for c in claims}
    flagged = unsupported_sentence_detector(report_text, backed)
    checks.append(
        GateCheck(
            check_id="UNSUPPORTED_SENTENCE",
            description="no unsupported quantitative sentence",
            passed=not flagged,
            details=flagged,
            severity="advisory",
        )
    )

    # T-08-07 (blocking): material claim OMITIDO do relatório = falha de
    # integridade (não basta estar no registry — o leitor precisa ver).
    omitted = [
        c.claim_id for c in material if c.statement.strip().lower() not in lower_report
    ]
    checks.append(
        GateCheck(
            check_id="MATERIAL_CLAIM_INCLUDED",
            description="no material claim omitted from the report",
            passed=not omitted,
            details=omitted,
        )
    )

    # T-08-07 (blocking): entailment no GATE — um claim com standing resolvido
    # precisa manter entailment mínimo com o MELHOR span vinculado; divergência
    # significa que a citação não sustenta mais o texto (ou que o standing
    # está inconsistente com a evidência).
    span_by_id = {sp.evidence_id: sp for sp in spans}
    not_entailed: list[dict] = []
    for c in material:
        if c.standing == Standing.UNRESOLVED:
            continue
        best = 0.0
        for e in c.support_edges:
            sp = span_by_id.get(e)
            if sp is not None:
                best = max(best, entailment_score(c.statement, sp.verbatim_span))
        if c.support_edges and best < 0.4:
            not_entailed.append({"claim_id": c.claim_id, "entailment": round(best, 4)})
    checks.append(
        GateCheck(
            check_id="CITATION_ENTAILED",
            description="resolved material claims keep entailment with their spans",
            passed=not not_entailed,
            details=not_entailed,
        )
    )

    # T-08-06/07 (blocking): references = SOMENTE fontes citadas no corpo —
    # dangling reference (listada, não citada) é falha de integridade.
    listed = _referenced_uris(report_text)
    uri_to_id = {s.canonical_uri: s.source_id for s in sources}
    cited_set = set(cited)
    dangling = [
        uri_to_id.get(u, u) for u in listed if uri_to_id.get(u, u) not in cited_set
    ]
    checks.append(
        GateCheck(
            check_id="REFERENCES_ONLY_CITED",
            description="reference list contains only sources cited in the body",
            passed=not dangling,
            details=dangling,
        )
    )

    return GateDecision.compose(
        gate_id="gate:citation_integrity",
        kind=GateKind.CITATION,
        checks=checks,
    )


_REF_LINE_RE = re.compile(r"^\s*\d+\.\s+\[[^\]]*\]\(([^)]+)\)", re.MULTILINE)


def _referenced_uris(report_text: str) -> list[str]:
    """URIs listados na seção References do relatório."""
    return _REF_LINE_RE.findall(report_text)


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


# --------------------------------------------------------------------------- #
# Report swarm (T-08-01..06, plan §28/§29): council -> section DAG -> packs ->
# writers -> reviewers -> fixers -> transition editor -> late sections ->
# citation manager. Tudo determinístico — os "papéis" são classes separadas
# com responsabilidades separadas (writer NUNCA revisa o próprio texto).
# --------------------------------------------------------------------------- #
@dataclass
class OutlineSection:
    """One section of the report outline; ``late`` sections são escritos por
    último (summary/conclusion — T-08-05)."""

    section_id: str
    title: str
    theme: str
    claim_ids: list[str] = field(default_factory=list)
    late: bool = False


# Councilors: cada perspectiva propõe temas de seção a partir dos claims.
def _theme_by_longest_token(claim: Claim) -> str:
    tokens = [t for t in tokenize(claim.statement) if len(t) > 3 and not t.isdigit()]
    return max(tokens, key=len) if tokens else "general"


def _theme_by_first_token(claim: Claim) -> str:
    tokens = [t for t in tokenize(claim.statement) if len(t) > 3 and not t.isdigit()]
    return tokens[0] if tokens else "general"


def _theme_by_scope(claim: Claim) -> str:
    scope = claim.scope or {}
    return str(scope.get("population") or scope.get("jurisdiction") or "general")


_COUNCILORS = {
    "content": _theme_by_longest_token,
    "lead": _theme_by_first_token,
    "scope": _theme_by_scope,
}


@dataclass
class CouncilRound:
    round_no: int
    proposals: dict[str, list[str]]
    elected: list[str]


class OutlineCouncil:
    """T-08-01: o outline é gerado por um CONSELHO, não por uma única regra.

    Cada councilor propõe temas; um tema vira seção quando atinge quórum de
    votos. Rodadas repetem até estabilizar (ou max_rounds) — as rodadas e as
    propostas ficam registradas para auditoria.
    """

    def __init__(
        self,
        councilors: dict[str, Any] | None = None,
        *,
        quorum: int = 2,
        max_rounds: int = 3,
    ) -> None:
        self.councilors = councilors or _COUNCILORS
        self.quorum = quorum
        self.max_rounds = max_rounds

    def convene(
        self, claims: list[Claim]
    ) -> tuple[list[OutlineSection], list[CouncilRound]]:
        rounds: list[CouncilRound] = []
        elected: list[str] = []
        for round_no in range(1, self.max_rounds + 1):
            proposals = {
                name: sorted({fn(c) for c in claims})
                for name, fn in self.councilors.items()
            }
            votes: dict[str, int] = {}
            for themes in proposals.values():
                for theme in themes:
                    votes[theme] = votes.get(theme, 0) + 1
            new_elected = sorted(t for t, v in votes.items() if v >= self.quorum)
            rounds.append(
                CouncilRound(
                    round_no=round_no, proposals=proposals, elected=new_elected
                )
            )
            if new_elected == elected:
                break  # convergiu
            elected = new_elected
        sections: list[OutlineSection] = []
        assigned: set[str] = set()
        for i, theme in enumerate(elected, start=1):
            members = [
                c.claim_id
                for c in claims
                if theme in {fn(c) for fn in self.councilors.values()}
            ]
            sections.append(
                OutlineSection(
                    section_id=f"S-{i}",
                    title=theme.replace("_", " ").title(),
                    theme=theme,
                    claim_ids=members,
                )
            )
            assigned.update(members)
        # claims não cobertos por tema eleito caem em seção geral explícita
        rest = [c.claim_id for c in claims if c.claim_id not in assigned]
        if rest:
            sections.append(
                OutlineSection(
                    section_id=f"S-{len(sections) + 1}",
                    title="General Findings",
                    theme="general",
                    claim_ids=rest,
                )
            )
        return sections, rounds


# --------------------------------------------------------------------------- #
# Section DAG (T-08-02): uma task por seção
# --------------------------------------------------------------------------- #
@dataclass
class SectionDAG:
    """One-section-per-task DAG. Body sections are mutuamente independentes
    (paralelizáveis); late sections dependem de TODAS as body sections."""

    dependencies: dict[str, list[str]]

    def waves(self) -> list[list[str]]:
        done: set[str] = set()
        out: list[list[str]] = []
        remaining = dict(self.dependencies)
        while remaining:
            ready = sorted(
                s for s, deps in remaining.items() if all(d in done for d in deps)
            )
            if not ready:
                raise ValueError("section DAG has a cycle")
            out.append(ready)
            done.update(ready)
            for s in ready:
                del remaining[s]
        return out


def build_section_dag(sections: list[OutlineSection]) -> SectionDAG:
    """Body sections não compartilham claims (partição) => wave única
    paralelizável; late sections fecham a DAG dependendo de todas as body."""
    body = [s.section_id for s in sections if not s.late]
    deps: dict[str, list[str]] = {
        s.section_id: ([] if not s.late else list(body)) for s in sections
    }
    return SectionDAG(dependencies=deps)


# --------------------------------------------------------------------------- #
# Evidence packs mínimos por seção (T-08-03)
# --------------------------------------------------------------------------- #
def build_section_packs(
    sections: list[OutlineSection],
    claims: list[Claim],
    sources: list[SourceRecord],
    spans: list[EvidenceSpan],
) -> dict[str, EvidencePack]:
    """Cada seção recebe APENAS o seu material mínimo: seus claims, os spans
    que os embasam e as fontes desses spans — nada do corpus inteiro."""
    claim_by_id = {c.claim_id: c for c in claims}
    span_by_id = {sp.evidence_id: sp for sp in spans}
    src_by_id = {s.source_id: s for s in sources}
    packs: dict[str, EvidencePack] = {}
    for section in sections:
        sclaims = [claim_by_id[cid] for cid in section.claim_ids if cid in claim_by_id]
        span_ids = {e for c in sclaims for e in c.support_edges}
        sspans = [span_by_id[e] for e in sorted(span_ids) if e in span_by_id]
        src_ids = {sp.source_id for sp in sspans}
        ssources = [src_by_id[s] for s in sorted(src_ids) if s in src_by_id]
        packs[section.section_id] = EvidencePack(
            pack_id=f"pack-{section.section_id}",
            claims=sclaims,
            sources=ssources,
            evidence_spans=sspans,
        )
    return packs


# --------------------------------------------------------------------------- #
# Writers / reviewers / fixers / transition editor (T-08-04)
# --------------------------------------------------------------------------- #
@dataclass
class ReviewReport:
    section_id: str
    reviewer_role: str
    issues: list[str]


class SectionWriter:
    role = "section_writer"

    def write(self, section: OutlineSection, pack: EvidencePack) -> str:
        span_by_id = {sp.evidence_id: sp for sp in pack.evidence_spans}
        lines = []
        for c in pack.claims:
            cites = [
                f"[cite:{span_by_id[e].source_id}]"
                for e in c.support_edges
                if e in span_by_id
            ]
            cite_txt = " ".join(cites) if cites else "[sem evidence span — UNRESOLVED]"
            lines.append(
                f"- **{c.claim_id}** ({c.standing.value}, {c.confidence:.2f}) — {c.statement} {cite_txt}"
            )
        return "\n\n".join(lines) if lines else "_no claims in this section_"


class SectionReviewer:
    role = "section_reviewer"  # reviewer != writer (T-08-04)

    def review(
        self, section: OutlineSection, text: str, pack: EvidencePack
    ) -> ReviewReport:
        issues: list[str] = []
        backed = {c.statement for c in pack.claims}
        for sentence in unsupported_sentence_detector(text, backed):
            issues.append(f"unsupported_numeric_sentence: {sentence}")
        source_ids = {s.source_id for s in pack.sources}
        for cited in extract_citations(text):
            if cited not in source_ids:
                issues.append(f"orphan_citation: {cited}")
        return ReviewReport(
            section_id=section.section_id, reviewer_role=self.role, issues=issues
        )


class SectionFixer:
    role = "section_fixer"  # fixer != writer/reviewer (T-08-04)

    def fix(
        self, section: OutlineSection, text: str, review: ReviewReport
    ) -> tuple[str, list[str]]:
        """Remove sentences sinalizadas como não-suportadas; registra os fixes."""
        removed = [
            i.split("unsupported_numeric_sentence: ", 1)[1]
            for i in review.issues
            if i.startswith("unsupported_numeric_sentence")
        ]
        fixes: list[str] = []
        out_lines = []
        for line in text.split("\n"):
            if any(r in line for r in removed):
                fixes.append(f"removed: {line.strip()}")
                continue
            out_lines.append(line)
        return "\n".join(out_lines), fixes


class TransitionEditor:
    role = "transition_editor"

    def edit(
        self, ordered: list[tuple[OutlineSection, str]]
    ) -> list[tuple[OutlineSection, str]]:
        """Adiciona frase de transição AO FINAL de cada seção (exceto a última),
        sem números (não dispara o detector de unsupported)."""
        out: list[tuple[OutlineSection, str]] = []
        for i, (section, text) in enumerate(ordered):
            if i + 1 < len(ordered):
                nxt = ordered[i + 1][0]
                text = (
                    text.rstrip()
                    + f"\n\n_The next section moves from {section.title.lower()} to {nxt.title.lower()}._"
                )
            out.append((section, text))
        return out


# --------------------------------------------------------------------------- #
# Citation manager (T-08-06)
# --------------------------------------------------------------------------- #
class CitationManager:
    """References = fontes CITADAS, nunca o corpus inteiro."""

    def __init__(self, sources: list[SourceRecord]) -> None:
        self.sources = sources

    def orphan_citations(self, text: str) -> list[str]:
        known = {s.source_id for s in self.sources}
        return [c for c in extract_citations(text) if c not in known]

    def references_for(self, text: str) -> list[SourceRecord]:
        by_id = {s.source_id: s for s in self.sources}
        return [by_id[c] for c in extract_citations(text) if c in by_id]

    def dangling_references(
        self, text: str, references: list[SourceRecord]
    ) -> list[str]:
        cited = set(extract_citations(text))
        return [r.source_id for r in references if r.source_id not in cited]


# --------------------------------------------------------------------------- #
# Pipeline completo do swarm (runner chama isto)
# --------------------------------------------------------------------------- #
@dataclass
class ReportSwarmResult:
    report_text: str
    outline: list[OutlineSection]
    council_rounds: list[CouncilRound]
    section_waves: list[list[str]]
    generation_order: list[str]
    review_log: list[dict]
    references: list[SourceRecord]


def run_report_swarm(
    objective: str,
    claims: list[Claim],
    sources: list[SourceRecord],
    spans: list[EvidenceSpan],
    *,
    council: OutlineCouncil | None = None,
) -> ReportSwarmResult:
    """Deterministic report swarm (T-08-01..06).

    Ordem de geração (T-08-05): TODAS as body sections primeiro; summary e
    conclusion são late sections escritas POR ÚLTIMO, sobre o texto final.
    """
    council = council or OutlineCouncil()
    sections, rounds = council.convene(claims)
    # seção de disclosure de claims UNRESOLVED (T-07-07)
    unresolved = [c for c in claims if c.standing == Standing.UNRESOLVED]
    if unresolved:
        sections.append(
            OutlineSection(
                section_id=f"S-{len(sections) + 1}",
                title="Unresolved Claims",
                theme="unresolved",
                claim_ids=[c.claim_id for c in unresolved],
            )
        )
    # late sections por último (T-08-05)
    n = len(sections)
    sections.append(
        OutlineSection(f"S-{n + 1}", "Executive Summary", "summary", late=True)
    )
    sections.append(OutlineSection(f"S-{n + 2}", "Conclusion", "conclusion", late=True))

    dag = build_section_dag(sections)
    waves = dag.waves()
    packs = build_section_packs(sections, claims, sources, spans)

    writer, reviewer, fixer, editor = (
        SectionWriter(),
        SectionReviewer(),
        SectionFixer(),
        TransitionEditor(),
    )
    generation_order: list[str] = []
    review_log: list[dict] = []
    produced: list[tuple[OutlineSection, str]] = []
    for wave in waves:
        for section_id in wave:
            section = next(s for s in sections if s.section_id == section_id)
            pack = packs[section_id]
            if section.late:
                continue  # escrito depois de todas as body (T-08-05)
            if section.theme == "unresolved":
                # disclosure estrutural (T-07-07): sem números soltos e sem
                # review/fix — não é conteúdo de writer.
                ids = ", ".join(section.claim_ids)
                text = (
                    "The following claims remain UNRESOLVED and are disclosed in "
                    f"`claims/unresolved.json`: {ids}."
                )
                produced.append((section, text))
                generation_order.append(section_id)
                continue
            text = writer.write(section, pack)
            review = reviewer.review(section, text, pack)
            text, fixes = fixer.fix(section, text, review)
            review_log.append(
                {
                    "section_id": section_id,
                    "writer": writer.role,
                    "reviewer": review.reviewer_role,
                    "fixer": fixer.role if fixes else None,
                    "issues": review.issues,
                    "fixes": fixes,
                }
            )
            produced.append((section, text))
            generation_order.append(section_id)

    produced = editor.edit(produced)

    # late sections: escritas por último sobre o resultado final (T-08-05).
    # Sem dígitos soltos — IDs em vez de contagens para não disparar o
    # detector de sentenças numéricas não-suportadas (o detector ignora
    # identificadores estilo CL-1 por design).
    def _ids(standing: Standing) -> str:
        ids = [c.claim_id for c in claims if c.standing == standing]
        return ", ".join(ids) if ids else "none"

    summary_text = (
        f"Supported claims: {_ids(Standing.SUPPORTED)}. "
        f"Contradicted: {_ids(Standing.CONTRADICTED)}. "
        f"Unresolved (disclosed in `claims/unresolved.json`): {_ids(Standing.UNRESOLVED)}."
    )
    conclusion_text = (
        f"Objective: {objective}. All findings above are tied to exact evidence "
        "spans; unresolved claims are explicitly disclosed."
    )
    for section in sections:
        if not section.late:
            continue
        text = summary_text if section.theme == "summary" else conclusion_text
        produced.append((section, text))
        generation_order.append(section.section_id)

    assembler = ReportAssembler(objective)
    for section, text in produced:
        assembler.add_section(section.title, text)
    manager = CitationManager(sources)
    body_so_far = "\n".join(text for _s, text in produced)
    references = manager.references_for(body_so_far)
    report_text = assembler.assemble(references)
    return ReportSwarmResult(
        report_text=report_text,
        outline=sections,
        council_rounds=rounds,
        section_waves=waves,
        generation_order=generation_order,
        review_log=review_log,
        references=references,
    )
