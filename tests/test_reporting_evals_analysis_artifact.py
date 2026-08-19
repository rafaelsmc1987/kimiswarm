"""Reporting, evals, analysis and artifact modules."""

from __future__ import annotations

from kdrx.analysis import Calculation, CalculationLedger, hash_artifact
from kdrx.artifact import (
    ExplorationNode,
    ExplorationTree,
    artifact_from_file,
    seal_artifact,
    verify_seal,
)
from kdrx.evals import EvalHarness, builtin_cases, run_case
from kdrx.reporting import (
    ReportAssembler,
    citation_integrity_gate,
    extract_citations,
    unsupported_sentence_detector,
)
from kdrx.schemas.artifact import ArtifactRecord
from kdrx.schemas.claims import Claim
from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
from kdrx.schemas.enums import ArtifactKind, ClaimImportance, SourceType, Standing


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def test_extract_citations():
    assert extract_citations("a [cite:S1] b [cite: S2] c [cite:S1]") == ["S1", "S2"]


def test_unsupported_sentence_detector():
    flagged = unsupported_sentence_detector(
        "Revenue was 5 million. The sky is blue.", {"revenue was 5 million"}
    )
    assert flagged == []


def test_unsupported_sentence_flags_number_without_backing():
    flagged = unsupported_sentence_detector("Revenue was 5 million.", set())
    assert len(flagged) == 1


def test_citation_integrity_gate_passes_backed_report():
    s1 = SourceRecord(source_id="S1", canonical_uri="https://a", title="A", source_type=SourceType.NEWS)
    c = Claim(
        claim_id="C1",
        statement="The model improved by 12 percent",
        importance=ClaimImportance.MAJOR,
        standing=Standing.SUPPORTED,
        support_edges=["EV1"],
    )
    sp = EvidenceSpan(evidence_id="EV1", source_id="S1", verbatim_span="improved by 12 percent")
    report = "The model improved by 12 percent [cite:S1]."
    gate = citation_integrity_gate(report, sources=[s1], claims=[c], spans=[sp])
    assert not gate.blocking()


def test_citation_integrity_gate_flags_unknown_citation():
    report = "Something happened [cite:MISSING]."
    gate = citation_integrity_gate(report, sources=[], claims=[], spans=[])
    assert any(c.check_id == "CITATION_EXISTS" and not c.passed for c in gate.checks)


def test_report_assembler_builds_references():
    s1 = SourceRecord(source_id="S1", canonical_uri="https://a", title="A")
    a = ReportAssembler("T")
    a.add_section("Intro", "Body [cite:S1]")
    out = a.assemble([s1])
    assert out.startswith("# T")
    assert "## References" in out
    assert "1. [A](https://a)" in out


# --------------------------------------------------------------------------- #
# Evals
# --------------------------------------------------------------------------- #
def test_builtin_cases_all_pass():
    harness = EvalHarness()
    for case in builtin_cases():
        harness.register(case)
    reports = harness.run_all()
    assert all(r.passed for r in reports)
    assert harness.regression_pass(reports)


def test_run_case_recall_precision():
    from kdrx.evals import EvalCase, SeededDefect

    case = EvalCase(
        case_id="c",
        description="d",
        sources=[SourceRecord(source_id="S", canonical_uri="https://fake", title="t")],
        trusted_uris={"https://trusted"},
        defects=[SeededDefect("d1", "fabricated_source", "x", expect=["S"])],
    )
    report = run_case(case)
    assert report.passed
    assert report.recall == 1.0


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def test_calculation_reproducible():
    def runner(inputs):
        return "sum=" + str(sum(int(v) for v in inputs.values()))

    calc = Calculation(
        calc_id="c1", inputs={"a": "1", "b": "2"}, output_hash=hash_artifact("sum=3")
    )
    assert calc.reproducible_from(runner)
    calc.output_hash = hash_artifact("sum=999")
    assert not calc.reproducible_from(runner)


def test_calculation_ledger_verify_all():
    def runner(inputs):
        return "x"

    ledger = CalculationLedger()
    ledger.add(Calculation(calc_id="c1", inputs={}, output_hash=hash_artifact("x")))
    assert ledger.verify_all({"c1": runner}) == []
    assert ledger.verify_all({}) == ["c1"]  # missing runner -> cannot reproduce


# --------------------------------------------------------------------------- #
# Artifact
# --------------------------------------------------------------------------- #
def test_seal_and_verify(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hello world")
    rec = artifact_from_file("A1", ArtifactKind.REPORT, p)
    assert verify_seal(rec, p)
    p.write_text("tampered")
    assert not verify_seal(rec, p)


def test_seal_artifact_from_bytes():
    rec = ArtifactRecord(artifact_id="A", kind=ArtifactKind.REPORT, path="x", content_hash="")
    rec = seal_artifact(rec, "payload")
    assert rec.seal_level.value == "level_1_hashed"
    assert rec.content_hash == hash_artifact("payload")


def test_exploration_tree_observed_vs_inferred():
    t = ExplorationTree()
    t.add(ExplorationNode("n1", "hypothesis", "h"))
    t.add(ExplorationNode("n2", "evidence", "e", parents=["n1"], inferred=True))
    assert [n.node_id for n in t.observed_nodes()] == ["n1"]
    assert [n.node_id for n in t.inferred_nodes()] == ["n2"]
    assert "inferred: true" in t.to_yaml()
