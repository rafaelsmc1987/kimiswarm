"""FASE 4 — state machine real, resume e hard gates (T-04-01..07).

Cobre: run-dir canônico, transições persistidas do manifest (crash/restart),
selo de hashes, resume sem repetir tasks fechadas, escrita atômica + safe_join,
delivery-manifest real, severidades blocking/advisory e verificação de
identidade mínima de fontes.
"""

from __future__ import annotations

import json

import pytest

from kdrx.retrieval import FileCorpus
from kdrx.runner import (
    build_contract,
    build_plan,
    execute_plan,
    prepare_run_dir,
    resume_run,
    run_file_research,
)
from kdrx.schemas.corpus import SourceRecord
from kdrx.schemas.enums import SourceType
from kdrx.schemas.gate import GateCheck, GateDecision
from kdrx.schemas.enums import GateKind
from kdrx.schemas.plan import RunManifest
from kdrx.state import RunState
from kdrx.verification import source_trust_gate


def _fresh_state(root, rid: str) -> RunState:
    st = RunState(root, rid)
    st.scaffold(
        RunManifest(run_id=rid, plan_id="p", contract_id="c", route="R4", root_dir="")
    )
    return st


def _make_corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "findings.md").write_text(
        "The new model improves accuracy by 12 percent on three datasets.\n"
        "Latency is 5 ms under load.\n",
        encoding="utf-8",
    )
    (corpus / "method.md").write_text("Training used 8 GPUs.\n", encoding="utf-8")
    return FileCorpus(corpus)


def _start_plan(tmp_path):
    corpus = _make_corpus(tmp_path)
    contract = build_contract("accuracy and latency of the model")
    plan = build_plan(contract, 2)
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    return corpus, plan, contract, state


# --------------------------------------------------------------------------- #
# T-04-02/T-04-03: transições de manifest + selo de hashes
# --------------------------------------------------------------------------- #
def test_manifest_transitions_and_hash_seal(tmp_path):
    corpus, plan, contract, state = _start_plan(tmp_path)
    result, _ex = execute_plan(plan, contract, corpus, state)
    assert not result.failed

    manifest = state.load_manifest()
    assert manifest.status == "succeeded"
    assert set(manifest.completed_tasks) >= {"T-RETRIEVE", "T-VERIFY"}
    assert manifest.gate_results.get("integrity") in ("pass", "warn")
    assert manifest.gate_results.get("security") == "pass"
    # Selo: cada artifact canônico tem hash; mutáveis NÃO entram
    assert manifest.artifact_hashes
    rel = {k.replace("\\", "/") for k in manifest.artifact_hashes}
    assert "manifest.json" not in rel and "events.jsonl" not in rel
    assert "delivery/report.md" in rel


def test_completion_fails_persisted_on_task_error(tmp_path):
    """Crash scenario: uma tarefa falha -> manifest persiste FAILED + failure."""
    corpus, plan, contract, state = _start_plan(tmp_path)

    # corrompe o corpus: zero-document corpus faz T-VERIFY levantar (B-06)
    class _EmptyCorpus(FileCorpus):
        def scan(self, *, extensions=None):
            return []

    result, _ex = execute_plan(plan, contract, _EmptyCorpus(tmp_path / "corpus"), state)
    assert result.failed, "wave 2 deve falhar sem fontes"
    manifest = state.load_manifest()
    assert manifest.status == "failed"
    assert "T-VERIFY" in manifest.failed_tasks


# --------------------------------------------------------------------------- #
# T-04-04: resume sem repetir tasks fechadas
# --------------------------------------------------------------------------- #
def test_resume_skips_completed_tasks(tmp_path):
    corpus, plan, contract, state = _start_plan(tmp_path)
    result1, _ = execute_plan(plan, contract, corpus, state)
    assert not result1.failed
    events1 = [
        json.loads(line)
        for line in state.read_text("events.jsonl").splitlines()
        if line.strip()
    ]
    assert any(e["kind"] == "task_started" for e in events1)

    pre_events = len(events1)
    result2, _ = resume_run(state, corpus)
    assert not result2.failed
    assert set(result2.completed) == set(result1.completed)

    events2 = [
        json.loads(line)
        for line in state.read_text("events.jsonl").splitlines()
        if line.strip()
    ]
    new_events = events2[pre_events:]
    new_started = [e for e in new_events if e["kind"] == "task_started"]
    assert new_started == [], f"resume NÃO deve re-executar tasks: {new_started}"
    assert any(e["kind"] == "task_resumed" for e in new_events)
    # provenance: plane re-consumido do disco
    m = state.load_manifest()
    assert m.metadata.get("hash_mismatch") in (None, [])


def test_resume_detects_hash_tampering(tmp_path):
    corpus, plan, contract, state = _start_plan(tmp_path)
    result, _ = execute_plan(plan, contract, corpus, state)
    assert not result.failed

    # tampa com delivery/report.md DEPOIS do selo
    state.write_text("delivery/report.md", "tampered content\n")
    rs = RunState(state.run_dir.parent, state.run_id)
    m = rs.resume()
    mismatches = m.metadata.get("hash_mismatch") or []
    norm = [p.replace("\\", "/") for p in mismatches]
    assert any("delivery/report.md" in p for p in norm), mismatches


# --------------------------------------------------------------------------- #
# T-04-05: escritas atômicas + path escape bloqueado
# --------------------------------------------------------------------------- #
def test_atomic_writes_leave_no_tmp(tmp_path, monkeypatch):
    state = _fresh_state(tmp_path / "runs", "atomic-test")
    state.write_text("x/a.txt", "hello")
    assert not list(state.run_dir.rglob("*.tmp*"))
    # falha no meio da escrita não deixa o destino corrompido
    import os as _os

    monkeypatch.setattr(_os, "replace", _raising_oserror)
    with pytest.raises(OSError):
        state.write_text("x/b.txt", "partial")
    # write_text deixou tmp órfão? não pode sobrar o destino corrompido
    assert not (state.run_dir / "x" / "b.txt").exists()


def _raising_oserror(*_a, **_k):
    raise OSError("disk full")


def test_path_escape_blocked(tmp_path):
    state = _fresh_state(tmp_path / "runs", "escape-test")
    with pytest.raises((ValueError, Exception)):
        state.write_text("../escape.txt", "nope")
    with pytest.raises((ValueError, Exception)):
        state.read_text("../../etc/passwd.txt")


# --------------------------------------------------------------------------- #
# T-04-06: delivery-manifest real
# --------------------------------------------------------------------------- #
def test_delivery_manifest_has_real_artifacts(tmp_path):
    corpus, plan, contract, state = _start_plan(tmp_path)
    result, _ = execute_plan(plan, contract, corpus, state)
    assert not result.failed
    dm = json.loads(state.read_text("delivery-manifest.json"))
    assert dm["artifact_open_test_passed"] is True
    assert dm["run_id"] == state.run_id
    assert dm["artifacts"], "delivery manifest deve listar artifacts reais"
    art = dm["artifacts"][0]
    expected = __import__("hashlib").sha256(
        (state.run_dir / "delivery" / "report.md").read_bytes()
    ).hexdigest()
    assert art["content_hash"] == expected
    assert (state.run_dir / "delivery" / "report.md").is_file()


# --------------------------------------------------------------------------- #
# T-04-07: severidades e gates duros
# --------------------------------------------------------------------------- #
def test_gate_severity_semantics():
    blocking_fail = GateDecision.compose(
        gate_id="g1",
        kind=GateKind.SOURCE,
        checks=[GateCheck(check_id="X", description="b", passed=False)],
    )
    assert blocking_fail.verdict == "fail"
    assert blocking_fail.blocking_reasons, "falha blocking gera blocking_reasons"

    advisory_only = GateDecision.compose(
        gate_id="g2",
        kind=GateKind.SOURCE,
        checks=[GateCheck(check_id="Y", description="a", passed=False, severity="advisory")],
    )
    assert advisory_only.verdict == "warn"
    assert not advisory_only.blocking(), "advisory-only não é blocking"


def test_source_trust_coi_only_is_warn_not_fail():
    src = SourceRecord(
        source_id="s1",
        canonical_uri="https://example.org/p",
        title="paper",
        source_type=SourceType.ACADEMIC_PAPER,
        content_hash="sha256:abc",
        conflicts_of_interest=["funded-by-x"],
    )
    g = source_trust_gate(src)
    assert g.verdict == "warn", g.verdict
    assert not g.blocking()


def test_source_trust_missing_identity_blocks():
    src = SourceRecord(
        source_id="s2",
        canonical_uri="https://example.org/p",
        title="paper",
        source_type=SourceType.UNKNOWN,  # TYPE check falha => blocking
        content_hash="",  # HASH check falha => blocking
    )
    g = source_trust_gate(src)
    assert g.verdict == "fail", g.verdict
    assert g.blocking()


def test_empty_corpus_does_not_succeed(tmp_path):
    """B-06: zero-document corpus => exit_code 1, manifest FAILED, sem delivery
    de sucesso."""
    corpus = tmp_path / "empty"
    corpus.mkdir()
    summary = run_file_research(corpus, "anything", tmp_path / "runs")
    assert summary["exit_code"] == 1
    assert "T-VERIFY" in summary["failed_tasks"]
    state = RunState(tmp_path / "runs", summary["run_id"])
    m = state.load_manifest()
    assert m.status == "failed"


# --------------------------------------------------------------------------- #
# T-04-01: layout canônico .research/runs/<id>
# --------------------------------------------------------------------------- #
def test_default_runs_root_layout(tmp_path):
    _make_corpus(tmp_path)
    contract = build_contract("layout check")
    plan = build_plan(contract, 2)
    state, _m = prepare_run_dir(plan, contract, tmp_path / ".research" / "runs")
    assert state.run_dir.parent.name == "runs"
    assert state.run_dir.parent.parent.name == ".research"
