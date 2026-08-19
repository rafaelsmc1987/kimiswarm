"""FASE 7: claims structure, entailment, edges, contradições, falsificação."""

from __future__ import annotations

import json

from kdrx.claims import (
    classify_edge_relation,
    decompose_into_claims,
    derive_edge,
    discover_contradiction_pairs,
    entailment_score,
    extract_scope,
    is_falsifiable,
    search_counterevidence,
    source_quality_score,
)
from kdrx.retrieval import FileCorpus
from kdrx.runner import run_file_research
from kdrx.schemas.claims import Claim
from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
from kdrx.schemas.enums import EdgeRelation, ExtractionStatus, QualityGrade, SourceType


def make_span(text: str, evidence_id: str = "EV-1", source_id: str = "file:a.md"):
    return EvidenceSpan(
        evidence_id=evidence_id, source_id=source_id, verbatim_span=text
    )


def make_source(**kw) -> SourceRecord:
    base = dict(
        source_id="file:a.md",
        canonical_uri="file:///a.md",
        title="a.md",
        source_type=SourceType.DATASET,
        content_hash="sha256:x",
        extraction_status=ExtractionStatus.EXTRACTED,
    )
    base.update(kw)
    return SourceRecord(**base)


# --------------------------------------------------------------------------- #
# T-07-01: decomposer estruturado
# --------------------------------------------------------------------------- #
def test_compound_statement_decomposes():
    claims = decompose_into_claims(
        "CL-1", "Accuracy improved by 12 percent and latency dropped to 5 ms"
    )
    assert len(claims) == 2
    assert claims[0].claim_id == "CL-1-1"
    assert claims[1].claim_id == "CL-1-2"
    assert "accuracy" in claims[0].statement.lower()
    assert "latency" in claims[1].statement.lower()


def test_atomic_statement_keeps_base_id():
    claims = decompose_into_claims("CL-7", "Accuracy improved by 12 percent")
    assert len(claims) == 1
    assert claims[0].claim_id == "CL-7"


def test_scope_extraction():
    scope = extract_scope("In 2021, among adults in Brazil, adoption was 55 percent")
    assert scope["time"] == "2021"
    assert scope["population"] == "adults"
    assert scope["jurisdiction"] == "brazil"


def test_falsifiability_requires_assertion():
    assert is_falsifiable("Accuracy was 88 percent on the benchmark")
    assert not is_falsifiable("42 results")  # número sem predicado
    assert not is_falsifiable("   ")


# --------------------------------------------------------------------------- #
# T-07-02: entailment verifier independente
# --------------------------------------------------------------------------- #
def test_entailment_full_vs_partial():
    claim = "Accuracy improves by 12 percent on the benchmark"
    full = entailment_score(claim, claim)
    assert full == 1.0
    # span cobre o sujeito mas diverge/falta o número => entailment parcial
    partial = entailment_score(claim, "Accuracy improves strongly on the benchmark")
    assert 0.4 <= partial < 0.9


def test_entailment_numeric_mismatch_capped():
    s = entailment_score("Latency is 5 ms under load", "Latency is 9 ms under load")
    # cobertura 5/6 (0.7 peso), número divergente (0.0) => ~0.583
    assert abs(s - 0.7 * (5 / 6)) < 1e-9


# --------------------------------------------------------------------------- #
# T-07-03: vocabulário completo de edge relations
# --------------------------------------------------------------------------- #
def test_classify_full_support_and_qualifies():
    claim = Claim(
        claim_id="c",
        statement="Accuracy was 88 percent in 2021",
        scope={"time": "2021"},
    )
    rel = classify_edge_relation(
        claim,
        "Accuracy was 88 percent in 2021",
        entailment=1.0,
        scope_match=True,
        temporal_match=True,
    )
    assert rel == EdgeRelation.SUPPORTS


def test_scope_mismatch_yields_qualifies():
    claim = Claim(
        claim_id="c",
        statement="Accuracy was 88 percent in 2021",
        scope={"time": "2021"},
    )
    span = "Accuracy was 88 percent overall"
    rel = classify_edge_relation(
        claim, span, entailment=0.9, scope_match=False, temporal_match=False
    )
    assert rel == EdgeRelation.QUALIFIES


def test_numeric_disagreement_with_overlap_contradicts():
    claim = Claim(claim_id="c", statement="Accuracy was 88 percent on benchmark")
    rel = classify_edge_relation(
        claim,
        "Accuracy was 82 percent on benchmark",
        entailment=0.7,
        scope_match=True,
        temporal_match=True,
    )
    assert rel == EdgeRelation.CONTRADICTS


def test_low_entailment_context_or_irrelevant():
    claim = Claim(claim_id="c", statement="Accuracy was 88 percent")
    rel = classify_edge_relation(
        claim,
        "some vague text mentioning accuracy",
        entailment=0.2,
        scope_match=True,
        temporal_match=True,
    )
    assert rel == EdgeRelation.CONTEXT_ONLY
    rel2 = classify_edge_relation(
        claim,
        "totally unrelated words here",
        entailment=0.0,
        scope_match=True,
        temporal_match=True,
    )
    assert rel2 == EdgeRelation.IRRELEVANT


# --------------------------------------------------------------------------- #
# T-07-04: descoberta automática de contradições
# --------------------------------------------------------------------------- #
def test_discovery_finds_numeric_and_polarity_pairs():
    claims = [
        Claim(claim_id="c1", statement="Latency is 5 ms under load"),
        Claim(claim_id="c2", statement="Latency is 9 ms under load"),
        Claim(claim_id="c3", statement="Method A improves accuracy"),
        Claim(claim_id="c4", statement="Method A does not improve accuracy"),
        Claim(claim_id="c5", statement="Completely different topic here"),
    ]
    pairs = set(discover_contradiction_pairs(claims))
    assert ("c1", "c2") in pairs  # numeric disagreement
    assert ("c3", "c4") in pairs  # polarity flip
    assert all("c5" not in p for p in pairs)


def test_pipeline_discovers_contradictions_end_to_end(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text(
        "The system latency is 5 ms under load with 42 nodes.\n"
    )
    (corpus / "b.md").write_text(
        "The system latency is 9 ms under load with 42 nodes.\n"
    )
    summary = run_file_research(corpus, "system latency under load", tmp_path / "runs")
    assert summary["exit_code"] == 0
    run_dir = tmp_path / "runs" / summary["run_id"]
    contra = json.loads(
        (run_dir / "claims" / "contradictions.json").read_text(encoding="utf-8")
    )
    assert contra, "descoberta automática deveria achar o par 5ms vs 9ms"
    cluster = contra[0]
    assert len(cluster["claims"]) == 2
    # standings refletem a contradição (edges CONTRADICTS persistidos)
    edges = (run_dir / "claims" / "edges.jsonl").read_text(encoding="utf-8")
    assert '"CONTRADICTS"' in edges


# --------------------------------------------------------------------------- #
# T-07-05: falsification swarm executado (busca ativa)
# --------------------------------------------------------------------------- #
def test_counterevidence_search_finds_numeric_disagreement(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("Latency is 5 ms under load\n")
    (corpus / "b.md").write_text("Latency is 9 ms under load\n")
    fc = FileCorpus(corpus)
    fc.scan()
    claim = Claim(claim_id="c1", statement="Latency is 5 ms under load")
    hits = search_counterevidence(claim, fc, own_source_id="a.md")
    assert hits and hits[0].doc_id == "b.md"
    assert hits[0].reason == "numeric_disagreement"
    # self-evidence nunca é refutação
    assert all(h.doc_id != "a.md" for h in hits)


def test_counterevidence_artifact_written(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("Latency is 5 ms with the new cache layer.\n")
    (corpus / "b.md").write_text("Latency is 9 ms with the new cache layer.\n")
    summary = run_file_research(corpus, "latency cache layer", tmp_path / "runs")
    run_dir = tmp_path / "runs" / summary["run_id"]
    hits = (run_dir / "claims" / "counterevidence.jsonl").read_text(encoding="utf-8")
    assert "numeric_disagreement" in hits


# --------------------------------------------------------------------------- #
# T-07-06: scores derivados, não constantes
# --------------------------------------------------------------------------- #
def test_derived_scores_vary_with_inputs():
    span = make_span("Accuracy improves by 12 percent on the benchmark dataset")
    claim = Claim(
        claim_id="c",
        statement="Accuracy improves by 12 percent on the benchmark dataset",
    )
    weak = make_source(quality_grade=QualityGrade.WEAK)
    strong = make_source(
        quality_grade=QualityGrade.EXCELLENT,
        date=__import__("datetime").datetime(2026, 1, 1),
    )
    e_weak = derive_edge(claim, span, source=weak, family_size=1)
    e_strong = derive_edge(claim, span, source=strong, family_size=1)
    assert e_weak.source_quality != e_strong.source_quality  # derivado, não 0.8 fixo
    assert e_strong.relation == EdgeRelation.SUPPORTS
    assert e_strong.entailment == 1.0
    assert e_weak.verifier == "deterministic-entailment-v1"
    assert any("derived:" in note for note in e_weak.limitations)


def test_independence_scales_with_family_size():
    span = make_span("x")
    claim = Claim(claim_id="c", statement="x")
    assert derive_edge(claim, span, source=None, family_size=1).independence == 1.0
    assert derive_edge(claim, span, source=None, family_size=4).independence == 0.25


def test_source_quality_score_derived():
    s = make_source(quality_grade=QualityGrade.UNVERIFIED, content_hash=None, date=None)
    base = source_quality_score(s)
    assert base == 0.4  # grade UNVERIFIED sem sinais extras
    s2 = make_source(quality_grade=QualityGrade.UNVERIFIED)
    assert source_quality_score(s2) > base  # hash + data conhecida contam


# --------------------------------------------------------------------------- #
# T-07-07: unresolved registry / disclosure
# --------------------------------------------------------------------------- #
def test_unresolved_registry_and_report_disclosure(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    # doc retrieved (overlap com o objetivo) + doc com claim mas sem span
    (corpus / "a.md").write_text("Accuracy was 88 percent on the public benchmark.\n")
    (corpus / "b.md").write_text("Latency is 5 ms under heavy load conditions.\n")
    summary = run_file_research(corpus, "accuracy benchmark", tmp_path / "runs")
    assert summary["exit_code"] == 0
    run_dir = tmp_path / "runs" / summary["run_id"]
    registry = json.loads(
        (run_dir / "claims" / "unresolved.json").read_text(encoding="utf-8")
    )
    assert registry, "claim sem span deveria ir para o registry"
    entry = [r for r in registry if "latency" in r["statement"].lower()]
    if entry:
        assert entry[0]["reason"] == "no_evidence_span"
    report = (run_dir / "delivery" / "report.md").read_text(encoding="utf-8")
    assert "Unresolved Claims" in report
    assert "claims/unresolved.json" in report
