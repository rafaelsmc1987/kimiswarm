"""FASE 8: report swarm — council, section DAG, packs, papéis, integridade."""

from __future__ import annotations

import json

from kdrx.reporting import (
    CitationManager,
    OutlineCouncil,
    OutlineSection,
    ReportAssembler,
    SectionFixer,
    SectionReviewer,
    SectionWriter,
    TransitionEditor,
    build_section_dag,
    build_section_packs,
    citation_integrity_gate,
    run_report_swarm,
)
from kdrx.runner import run_file_research
from kdrx.schemas.claims import Claim
from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
from kdrx.schemas.enums import GateVerdict, SourceType, Standing


def make_claims() -> list[Claim]:
    return [
        Claim(
            claim_id="CL-1",
            statement="Accuracy was 88 percent on the benchmark",
            support_edges=["EV-1"],
            standing=Standing.SUPPORTED,
            confidence=0.9,
        ),
        Claim(
            claim_id="CL-2",
            statement="Latency is 5 ms under load",
            support_edges=["EV-2"],
            standing=Standing.SUPPORTED,
            confidence=0.8,
        ),
        Claim(
            claim_id="CL-3",
            statement="Cost dropped for users",
            support_edges=[],
            standing=Standing.UNRESOLVED,
        ),
    ]


def make_sources() -> list[SourceRecord]:
    return [
        SourceRecord(
            source_id="file:a.md",
            canonical_uri="file:///a.md",
            title="a.md",
            source_type=SourceType.DATASET,
        ),
        SourceRecord(
            source_id="file:b.md",
            canonical_uri="file:///b.md",
            title="b.md",
            source_type=SourceType.DATASET,
        ),
        SourceRecord(
            source_id="file:unused.md",
            canonical_uri="file:///unused.md",
            title="unused.md",
            source_type=SourceType.DATASET,
        ),
    ]


def make_spans() -> list[EvidenceSpan]:
    return [
        EvidenceSpan(
            evidence_id="EV-1",
            source_id="file:a.md",
            verbatim_span="Accuracy was 88 percent on the benchmark",
        ),
        EvidenceSpan(
            evidence_id="EV-2",
            source_id="file:b.md",
            verbatim_span="Latency is 5 ms under load",
        ),
    ]


# --------------------------------------------------------------------------- #
# T-08-01: outline council por rodadas
# --------------------------------------------------------------------------- #
def test_council_generates_outline_in_rounds():
    council = OutlineCouncil()
    sections, rounds = council.convene(make_claims())
    assert rounds, "conselho precisa de ao menos uma rodada registrada"
    assert rounds[-1].elected, "algum tema deve ser eleito por quórum"
    # todo claim cai em exatamente uma seção
    all_ids = [cid for s in sections for cid in s.claim_ids]
    assert sorted(all_ids) == ["CL-1", "CL-2", "CL-3"]


def test_council_converges_and_logs_each_round():
    _, rounds = OutlineCouncil().convene(
        make_claims()
        + [Claim(claim_id="CL-4", statement="Accuracy improved again in 2024")]
    )
    rounds_no = [r.round_no for r in rounds]
    assert rounds_no == list(range(1, len(rounds) + 1))  # sequencial
    assert all(r.proposals for r in rounds)  # cada rodada tem propostas


# --------------------------------------------------------------------------- #
# T-08-02: section DAG one-section-per-task
# --------------------------------------------------------------------------- #
def test_section_dag_parallelizes_body_and_serializes_late():
    sections, _ = OutlineCouncil().convene(make_claims())
    n = len(sections)
    sections.append(OutlineSection(f"S-{n + 1}", "Summary", "summary", late=True))
    sections.append(OutlineSection(f"S-{n + 2}", "Conclusion", "conclusion", late=True))
    dag = build_section_dag(sections)
    waves = dag.waves()
    body_wave = waves[0]
    assert len(body_wave) >= 2, "seções de corpo são paralelizáveis (mesma wave)"
    # late sections na última wave, depois de TODAS as body
    assert waves[-1] == sorted(s.section_id for s in sections if s.late)
    flat = [s for w in waves for s in w]
    assert len(flat) == len(sections)


# --------------------------------------------------------------------------- #
# T-08-03: evidence packs mínimos
# --------------------------------------------------------------------------- #
def test_section_packs_are_minimal():
    sections, _ = OutlineCouncil().convene(make_claims())
    packs = build_section_packs(sections, make_claims(), make_sources(), make_spans())
    for section in sections:
        pack = packs[section.section_id]
        pack_claim_ids = {c.claim_id for c in pack.claims}
        assert pack_claim_ids == set(section.claim_ids)
        # spans do pack: somente os que embasam os claims da seção
        valid = {e for c in pack.claims for e in c.support_edges}
        assert {sp.evidence_id for sp in pack.evidence_spans} <= valid
        # fontes do pack: somente as dos spans incluídos
        assert {s.source_id for s in pack.sources} <= {
            sp.source_id for sp in pack.evidence_spans
        }
        assert "file:unused.md" not in {s.source_id for s in pack.sources}


# --------------------------------------------------------------------------- #
# T-08-04: papéis separados (writer != reviewer != fixer != editor)
# --------------------------------------------------------------------------- #
def test_reviewer_catches_and_fixer_removes_unsupported_sentence():
    sections, _ = OutlineCouncil().convene(make_claims())
    packs = build_section_packs(sections, make_claims(), make_sources(), make_spans())
    section = next(s for s in sections if "CL-1" in s.claim_ids)
    writer, reviewer, fixer = SectionWriter(), SectionReviewer(), SectionFixer()
    assert writer.role != reviewer.role != fixer.role
    text = writer.write(section, packs[section.section_id])
    poisoned = text + "\n\nThe cost was 42 million dollars last year."
    review = reviewer.review(section, poisoned, packs[section.section_id])
    assert any("unsupported_numeric_sentence" in i for i in review.issues)
    fixed, fixes = fixer.fix(section, poisoned, review)
    assert fixes and "42 million" not in fixed
    assert "88 percent" in fixed  # conteúdo suportado preservado


def test_transition_editor_bridges_sections():
    sections, _ = OutlineCouncil().convene(make_claims())
    pairs = [(s, f"body of {s.title}") for s in sections[:2]]
    edited = TransitionEditor().edit(pairs)
    assert "next section" in edited[0][1]
    assert "next section" not in edited[-1][1]


# --------------------------------------------------------------------------- #
# T-08-05: summary/conclusion tardios
# --------------------------------------------------------------------------- #
def test_late_sections_generated_last():
    result = run_report_swarm("objective", make_claims(), make_sources(), make_spans())
    order = result.generation_order
    late_ids = [s.section_id for s in result.outline if s.late]
    assert order[-len(late_ids) :] == late_ids, "summary/conclusion escritos por último"
    body_ids = [s.section_id for s in result.outline if not s.late]
    assert order[: len(body_ids)] == body_ids


# --------------------------------------------------------------------------- #
# T-08-06: citation manager — sem orphan/dangling
# --------------------------------------------------------------------------- #
def test_citation_manager_no_orphans_no_dangling():
    result = run_report_swarm("objective", make_claims(), make_sources(), make_spans())
    manager = CitationManager(make_sources())
    assert manager.orphan_citations(result.report_text) == []
    assert manager.dangling_references(result.report_text, result.references) == []
    # fonte não citada (file:unused.md) NÃO entra nas references
    assert "file:unused.md" not in {r.source_id for r in result.references}
    assert "## References" in result.report_text


def test_orphan_and_dangling_detected():
    manager = CitationManager(make_sources())
    assert manager.orphan_citations("see [cite:file:ghost.md]") == ["file:ghost.md"]
    refs = [make_sources()[2]]  # unused.md listada mas não citada
    assert manager.dangling_references("see [cite:file:a.md]", refs) == [
        "file:unused.md"
    ]


# --------------------------------------------------------------------------- #
# T-08-07: hard final integrity
# --------------------------------------------------------------------------- #
def _gate_for(report, **kw):
    return citation_integrity_gate(
        report,
        sources=kw.get("sources", make_sources()),
        claims=kw.get("claims", make_claims()),
        spans=kw.get("spans", make_spans()),
    )


def test_omitted_material_claim_blocks():
    result = run_report_swarm("objective", make_claims(), make_sources(), make_spans())
    # remove a frase do CL-1 do relatório => claim material omitido
    tampered = result.report_text.replace(
        "Accuracy was 88 percent on the benchmark", "Accuracy was very high"
    )
    gate = _gate_for(tampered)
    assert gate.verdict == GateVerdict.FAIL
    check = [c for c in gate.checks if c.check_id == "MATERIAL_CLAIM_INCLUDED"][0]
    assert check.passed is False
    assert check.severity == "blocking"


def test_citation_entailment_checked_in_gate():
    result = run_report_swarm("objective", make_claims(), make_sources(), make_spans())
    gate = _gate_for(result.report_text)
    check = [c for c in gate.checks if c.check_id == "CITATION_ENTAILED"][0]
    assert check.passed is True
    # span corrompido => entailment quebra => FAIL
    bad_spans = [
        EvidenceSpan(
            evidence_id="EV-1", source_id="file:a.md", verbatim_span="zzz qqq"
        ),
        *make_spans()[1:],
    ]
    gate2 = _gate_for(result.report_text, spans=bad_spans)
    assert gate2.verdict == GateVerdict.FAIL


def test_dangling_reference_fails_gate():
    # relatório com reference NÃO citada no corpo
    assembler = ReportAssembler("t")
    assembler.add_section(
        "Findings",
        "- **CL-1** (supported, 0.90) — Accuracy was 88 percent on the benchmark [cite:file:a.md]",
    )
    report = assembler.assemble(make_sources())  # TODAS as fontes listadas
    gate = _gate_for(report)
    check = [c for c in gate.checks if c.check_id == "REFERENCES_ONLY_CITED"][0]
    assert check.passed is False
    assert "file:unused.md" in check.details
    assert gate.verdict == GateVerdict.FAIL


def test_integrity_blocks_pipeline_when_claim_omitted(tmp_path):
    """Report adulterado (claim removido) => verify/run falham (hard gate)."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("Accuracy was 88 percent on the public benchmark.\n")
    (corpus / "b.md").write_text("Latency is 5 ms under heavy load conditions.\n")
    summary = run_file_research(corpus, "accuracy benchmark", tmp_path / "runs")
    assert summary["exit_code"] == 0
    run_dir = tmp_path / "runs" / summary["run_id"]

    # UTF-8/open test: o relatório abre como UTF-8 válido
    raw = (run_dir / "delivery" / "report.md").read_bytes()
    raw.decode("utf-8")

    # adultera: remove claim do corpo => re-verify no disco deve BLOQUEAR
    report = (run_dir / "delivery" / "report.md").read_text(encoding="utf-8")
    (run_dir / "delivery" / "report.md").write_text(
        report.replace(
            "Latency is 5 ms under heavy load conditions", "Latency is fine"
        ),
        encoding="utf-8",
    )
    from kdrx.cli import main

    rc = main(["verify", "--run-dir", str(run_dir)])
    assert rc != 0, "integrity hard gate deve bloquear claim omitido"


def test_swarm_artifacts_persisted(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("Accuracy was 88 percent on the public benchmark.\n")
    (corpus / "b.md").write_text("Latency is 5 ms under heavy load conditions.\n")
    summary = run_file_research(corpus, "accuracy benchmark", tmp_path / "runs")
    assert summary["exit_code"] == 0, json.dumps(summary)
    run_dir = tmp_path / "runs" / summary["run_id"]
    outline = json.loads(
        (run_dir / "delivery" / "outline.json").read_text(encoding="utf-8")
    )
    assert outline["council_rounds"] and outline["sections"]
    dag = json.loads(
        (run_dir / "delivery" / "section_dag.json").read_text(encoding="utf-8")
    )
    assert dag["waves"]
    log = json.loads(
        (run_dir / "delivery" / "swarm_log.json").read_text(encoding="utf-8")
    )
    assert log["generation_order"][-2:] == [
        s["section_id"] for s in outline["sections"] if s["late"]
    ]
