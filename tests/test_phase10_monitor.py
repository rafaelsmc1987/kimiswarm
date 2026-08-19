"""FASE 10: monitoring (delta, retraction alerts, recompute, diffs) e
governed learning."""

from __future__ import annotations

import json

import pytest

from kdrx.claims import recompute_standings
from kdrx.evals import LEARNING_STAGES, LearningPipeline
from kdrx.reporting import diff_reports
from kdrx.retrieval import (
    SavedQuery,
    SavedQueryStore,
    delta_sources,
    snapshot_corpus_hashes,
)
from kdrx.schemas.claims import Claim
from kdrx.schemas.corpus import EvidenceSpan, SourceRecord
from kdrx.schemas.enums import RetractionStatus, Standing
from kdrx.verification import retraction_alerts


# --------------------------------------------------------------------------- #
# T-10-01: saved queries + delta retrieval
# --------------------------------------------------------------------------- #
@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.md").write_text("alpha content\n", encoding="utf-8")
    (root / "b.md").write_text("beta content\n", encoding="utf-8")
    return root


def test_delta_detects_added_changed_removed(corpus):
    first = snapshot_corpus_hashes(corpus)
    assert set(first) == {"a.md", "b.md"}

    # arquivo novo => added
    (corpus / "c.md").write_text("gamma content\n", encoding="utf-8")
    d1 = delta_sources(first, snapshot_corpus_hashes(corpus))
    assert d1.added == ["c.md"] and not d1.changed and not d1.removed
    assert d1.has_delta

    # edição semântica => changed
    prev = snapshot_corpus_hashes(corpus)
    (corpus / "a.md").write_text("alpha edited content\n", encoding="utf-8")
    d2 = delta_sources(prev, snapshot_corpus_hashes(corpus))
    assert d2.changed == ["a.md"] and not d2.added and not d2.removed

    # remoção => removed
    prev = snapshot_corpus_hashes(corpus)
    (corpus / "b.md").unlink()
    d3 = delta_sources(prev, snapshot_corpus_hashes(corpus))
    assert d3.removed == ["b.md"]

    # mesmo conteúdo (re-save idêntico) => sem delta
    same = snapshot_corpus_hashes(corpus)
    assert not delta_sources(same, same).has_delta


def test_saved_query_store_roundtrip(tmp_path):
    store = SavedQueryStore(tmp_path / "queries.json")
    assert store.load() == []
    store.add(SavedQuery(query="latency SLO", corpus_dir="corpusA", saved_at="t1"))
    store.add(SavedQuery(query="latency SLO", corpus_dir="corpusA", saved_at="t2"))  # dup
    store.add(SavedQuery(query="accuracy", corpus_dir="corpusA", saved_at="t3"))
    loaded = store.load()
    assert [(q.query, q.saved_at) for q in loaded] == [
        ("latency SLO", "t1"), ("accuracy", "t3")
    ]


def test_cli_monitor_full_flow(tmp_path, capsys):
    from kdrx.cli import main

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("alpha\n", encoding="utf-8")
    state = tmp_path / "monitor-state.json"

    # 1a chamada: tudo "added" (baseline)
    assert main(["monitor", "--corpus", str(corpus), "--state", str(state),
                 "--save-query", "watch accuracy", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["added"] == ["a.md"] and out["has_delta"] is True
    assert out["saved_queries"] == 1

    # 2a chamada sem mudança: sem delta; save-query duplicada não repete
    assert main(["monitor", "--corpus", str(corpus), "--state", str(state),
                 "--save-query", "watch accuracy", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["has_delta"] is False and out["saved_queries"] == 1

    # fonte nova => delta detecta
    (corpus / "b.md").write_text("beta\n", encoding="utf-8")
    assert main(["monitor", "--corpus", str(corpus), "--state", str(state),
                 "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["added"] == ["b.md"]
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["queries"][0]["query"] == "watch accuracy"


# --------------------------------------------------------------------------- #
# T-10-02: retraction / correction alerts
# --------------------------------------------------------------------------- #
def _retraction_fixture(status=RetractionStatus.RETRACTED):
    src = SourceRecord(
        source_id="S1",
        canonical_uri="https://s.example.com/1",
        title="paper",
        retraction_status=status,
    )
    clean = SourceRecord(
        source_id="S2", canonical_uri="https://s.example.com/2", title="clean"
    )
    claims = [
        Claim(claim_id="C-FULL", statement="A only", support_edges=["E1"]),
        Claim(claim_id="C-PART", statement="A and B", support_edges=["E1", "E2"]),
        Claim(claim_id="C-CLEAN", statement="B only", support_edges=["E2"]),
    ]
    spans = [
        EvidenceSpan(evidence_id="E1", source_id="S1", verbatim_span="lat is 5 ms"),
        EvidenceSpan(evidence_id="E2", source_id="S2", verbatim_span="acc 88 percent"),
    ]
    return [src, clean], claims, spans


def test_retraction_alert_invalidates_dependent_claims():
    sources, claims, spans = _retraction_fixture()
    alerts = retraction_alerts(sources, claims, spans)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.source_id == "S1"
    assert (alert.previous_status, alert.current_status) == ("none", "retracted")
    assert alert.affected_claims == ["C-FULL", "C-PART"]
    # S1 é a ÚNICA fonte de C-FULL => fully invalidated; C-PART ainda tem S2
    assert alert.fully_invalidated_claims == ["C-FULL"]


def test_alert_only_fires_on_status_change():
    sources, claims, spans = _retraction_fixture()
    # snapshot anterior JÁ marcava retracted => sem alerta duplicado
    assert (
        retraction_alerts(sources, claims, spans,
                          prior_status={"S1": "retracted", "S2": "none"}) == []
    )
    # corrected também dispara
    sources2, _, _ = _retraction_fixture(status=RetractionStatus.CORRECTED)
    alerts = retraction_alerts(sources2, claims, spans)
    assert len(alerts) == 1 and alerts[0].current_status == "corrected"
    # fonte limpa nunca dispara
    assert alerts[0].source_id != "S2"


# --------------------------------------------------------------------------- #
# T-10-03: standing recompute (shadow, sem mutação)
# --------------------------------------------------------------------------- #
def test_recompute_standings_detects_change_without_mutating():
    claims = [
        Claim(
            claim_id="CL-OK",
            statement="Accuracy was 88 percent on the benchmark",
            standing=Standing.UNRESOLVED,
            support_edges=["EV-A"],
        ),
        Claim(claim_id="CL-ORPHAN", statement="Latency is 5 ms",
              standing=Standing.SUPPORTED),
    ]
    spans = [
        EvidenceSpan(
            evidence_id="EV-A",
            source_id="S-A",
            verbatim_span="Accuracy was 88 percent on the benchmark",
        )
    ]
    sources = [
        SourceRecord(
            source_id="S-A", canonical_uri="file:///a.md", title="a.md"
        )
    ]
    result = recompute_standings(claims, spans, sources)
    by_id = {r["claim_id"]: r for r in result}

    # CL-OK ganhou evidence => standing deixa de ser UNRESOLVED
    assert by_id["CL-OK"]["old_standing"] == "unresolved"
    assert by_id["CL-OK"]["new_standing"] != "unresolved"
    assert by_id["CL-OK"]["changed"] is True
    # CL-ORPHAN perdeu suporte => deixa de ser SUPPORTED
    assert by_id["CL-ORPHAN"]["new_standing"] == "unresolved"
    assert by_id["CL-ORPHAN"]["changed"] is True
    # shadow recompute NÃO muta os claims originais
    assert claims[0].standing == Standing.UNRESOLVED
    assert claims[1].standing == Standing.SUPPORTED


# --------------------------------------------------------------------------- #
# T-10-04: report diffs
# --------------------------------------------------------------------------- #
_OLD = "# obj\n\n## Findings\n\n- **CL-1** (supported, 0.90) — accuracy 88 percent [cite:file:a.md]\n\n## References\n\nold\n"
_NEW = "# obj\n\n## Findings\n\n- **CL-1** (contradicted, 0.40) — accuracy 5 ms [cite:file:b.md]\n- **CL-2** (supported, 0.80) — latency 5 ms [cite:file:b.md]\n\n## Summary\n\nnew section body\n"


def test_diff_reports_captures_all_change_kinds():
    d = diff_reports(_OLD, _NEW)
    assert d.sections_added == ["Summary"]
    assert d.sections_removed == ["References"]
    assert d.sections_changed == ["Findings"]
    assert d.claims_added == ["CL-2"]
    assert d.claims_removed == []
    assert d.standing_changes == {"CL-1": {"from": "supported", "to": "contradicted"}}
    assert d.has_changes


def test_diff_reports_identical_is_clean():
    d = diff_reports(_OLD, _OLD)
    assert not d.has_changes
    assert d.as_dict()["standing_changes"] == {}


# --------------------------------------------------------------------------- #
# T-10-05: governed learning pipeline
# --------------------------------------------------------------------------- #
def _passing_reports():
    from kdrx.evals import EvalHarness, builtin_cases

    harness = EvalHarness()
    for case in builtin_cases():
        harness.register(case)
    return harness.run_all()


def test_learning_full_path_promotes():
    pipe = LearningPipeline()
    pipe.observe("retraction alert on S1", source="monitor")
    pipe.propose("cand-1", {"threshold_bump": "1.2.0"})
    gate = pipe.evaluate("cand-1", _passing_reports())
    assert gate.passed
    assert pipe.approve("cand-1", approver="human-reviewer")
    assert pipe.canary("cand-1", passed=True)
    assert pipe.promote("cand-1")
    assert pipe.stage_of("cand-1") == "promotion"
    assert list(LEARNING_STAGES)[-1] == "promotion"


def test_learning_NEVER_promotes_without_eval():
    """Promotion regression: sem eval passado, promotion é IMPOSSÍVEL."""
    pipe = LearningPipeline()
    pipe.propose("cand-x", {})
    assert pipe.promote("cand-x") is False
    assert pipe.stage_of("cand-x") == "candidate"
    rec = pipe.registry()["candidates"]["cand-x"]
    rejected = [h for h in rec["history"] if h["event"] == "promotion_rejected"]
    assert rejected and "missing_passing_eval" in rejected[0]["blockers"]
    # aprovação sem eval também é bloqueada
    assert pipe.approve("cand-x", "someone") is False
    assert pipe.promote("cand-x") is False


def test_learning_eval_failure_blocks_everything_downstream():
    from kdrx.evals import EvalReport

    pipe = LearningPipeline()
    pipe.propose("cand-bad", {})
    bad = EvalReport(
        case_id="x",
        expected={"fabricated_source": ["F1"]},
        detected={"fabricated_source": []},
    )
    gate = pipe.evaluate("cand-bad", [bad])
    assert not gate.passed
    assert pipe.approve("cand-bad", "human") is False
    assert pipe.canary("cand-bad", passed=True) is False  # canary exige approval
    assert pipe.promote("cand-bad") is False
    assert pipe.stage_of("cand-bad") == "candidate"


def test_learning_canary_failure_blocks_promotion():
    pipe = LearningPipeline()
    pipe.propose("cand-c", {})
    pipe.evaluate("cand-c", _passing_reports())
    assert pipe.approve("cand-c", "human")
    assert pipe.canary("cand-c", passed=False) is False
    assert pipe.promote("cand-c") is False
    # canary OK posterior APÓS aprovação ainda funciona
    assert pipe.canary("cand-c", passed=True)
    assert pipe.promote("cand-c")


def test_learning_unknown_candidate_raises():
    pipe = LearningPipeline()
    with pytest.raises(KeyError):
        pipe.promote("ghost")
