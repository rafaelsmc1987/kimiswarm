"""End-to-end offline pipeline (routes R3/R4)."""

from __future__ import annotations

import json

import pytest

from kdrx.runner import (
    PlanImportError,
    build_contract,
    build_plan,
    import_plan_into_run,
    prepare_run_dir,
    run_file_research,
)
from kdrx.schemas.enums import TaskStatus
from kdrx.state import hash_file


def test_run_file_research_end_to_end(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "findings.md").write_text(
        "The new model improves accuracy by 12 percent on three datasets.\n"
        "Latency is 5 ms under load.\n"
    )
    (corpus / "method.md").write_text("Training used 8 GPUs.\n")

    runs = tmp_path / "runs"
    summary = run_file_research(corpus, "accuracy and latency of the model", runs)

    assert summary["exit_code"] == 0
    assert summary["plan_gate"] == "pass"
    assert summary["documents"] == 2
    assert summary["failed_tasks"] == []

    run_dir = runs / summary["run_id"]
    report = (run_dir / "delivery" / "report.md").read_text(encoding="utf-8")
    assert "accuracy" in report.lower()

    integrity = json.loads(
        (run_dir / "verification" / "integrity.json").read_text(encoding="utf-8")
    )
    assert integrity["verdict"] in ("pass", "warn")

    security = json.loads(
        (run_dir / "verification" / "security.json").read_text(encoding="utf-8")
    )
    assert security["verdict"] == "pass"

    # claims and standings persisted
    standings = (run_dir / "claims" / "standings.jsonl").read_text(encoding="utf-8")
    assert "standing" in standings


def test_run_file_research_blocks_on_bad_plan(tmp_path):
    # A corpus with no text still yields a valid plan gate; the pipeline must
    # complete without failing even with zero documents.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "empty.txt").write_text("")
    summary = run_file_research(corpus, "anything", tmp_path / "runs")
    assert summary["exit_code"] == 0
    assert summary["documents"] == 1


def test_run_dir_persists_real_outputs_per_task(tmp_path):
    """T-02-07: o run dir guarda paths e outputs reais produzidos por cada
    tarefa declarada no plano — nada de placeholders."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "findings.md").write_text(
        "The new model improves accuracy by 12 percent on three datasets.\n"
        "Latency is 5 ms under load.\n"
    )

    summary = run_file_research(corpus, "accuracy and latency", tmp_path / "runs")
    assert summary["exit_code"] == 0
    run_dir = tmp_path / "runs" / summary["run_id"]

    import json as _json

    plan = _json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    declared = [out for t in plan["tasks"] for out in t["outputs"]]
    assert declared, "plano deve declarar outputs por tarefa"

    for rel in declared:
        path = run_dir / rel
        assert path.is_file(), f"output declarado ausente no disco: {rel}"
        assert path.stat().st_size > 0, f"output declarado vazio: {rel}"

    # claims persistidas DEPOIS do standing final (bug corrigido na PR-01)
    claims = [
        _json.loads(line)
        for line in (run_dir / "claims" / "claims.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert claims, "claims devem existir"
    assert all("standing" in c for c in claims)

    # event log real: ciclo de vida de cada tarefa
    events = [
        _json.loads(line)
        for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kinds = {e["kind"] for e in events}
    assert "task_started" in kinds and "task_succeeded" in kinds
    assert not any(e["kind"] == "task_failed" for e in events)


# --------------------------------------------------------------------------- #
# SW-02 PR-A: import gate + provenance (D1/D4)
# --------------------------------------------------------------------------- #
def test_prepare_run_dir_writes_scaffold_provenance(tmp_path):
    """D4: o scaffold grava metadata['plan'] com sha256 dos bytes persistidos."""
    contract = build_contract("provenance objective")
    plan = build_plan(contract, 2)
    state, manifest = prepare_run_dir(plan, contract, tmp_path / "runs")
    meta = manifest.metadata["plan"]
    assert meta["source"] == "scaffold-default"
    assert meta["review_approved"] is False
    assert meta["revision"] == 0
    assert meta["imported_at"] is None
    assert meta["sha256"] == hash_file(state.run_dir / "plan.json")


def test_import_plan_into_run_happy_path(tmp_path):
    """D1.7: waves sobrescritas pela derivacao; revision incrementa; evento."""
    contract = build_contract("import objective")
    plan = build_plan(contract, 2)
    state, _manifest = prepare_run_dir(plan, contract, tmp_path / "runs")
    plan.tasks[0].wave = 99  # wave declarada absurda; sem deps -> derivada 0

    imported = import_plan_into_run(
        state, plan, contract, source="manual", review_approved=True
    )
    assert imported["source"] == "manual"
    assert imported["review_approved"] is True
    assert imported["revision"] == 1
    assert imported["sha256"] == hash_file(state.run_dir / "plan.json")

    persisted = json.loads(state.read_text("plan.json"))
    assert persisted["tasks"][0]["wave"] == 0
    assert set(persisted["waves"]) == {"0", "1", "2", "3"}
    events = [e for e in state.iter_events() if e["kind"] == "plan_imported"]
    assert len(events) == 1
    assert events[0]["plan_hash"] == imported["sha256"]
    assert state.load_manifest().metadata["plan"] == imported

    # re-import enquanto PENDING e permitido e incrementa revision (D3/D4)
    imported2 = import_plan_into_run(
        state, plan, contract, source="council-imported", review_approved=True
    )
    assert imported2["revision"] == 2
    assert imported2["source"] == "council-imported"


def test_import_plan_identity_mismatch_blocks(tmp_path):
    contract = build_contract("import objective")
    plan = build_plan(contract, 2)
    state, _m = prepare_run_dir(plan, contract, tmp_path / "runs")
    wrong = plan.model_copy(update={"plan_id": "plan-other"})
    with pytest.raises(PlanImportError) as excinfo:
        import_plan_into_run(
            state, wrong, contract, source="manual", review_approved=False
        )
    assert excinfo.value.exit_code == 4
    # validate-then-write: plan.json intacto
    assert json.loads(state.read_text("plan.json"))["plan_id"] == plan.plan_id


def test_import_plan_after_execution_is_forbidden(tmp_path):
    contract = build_contract("import objective")
    plan = build_plan(contract, 2)
    state, _m = prepare_run_dir(plan, contract, tmp_path / "runs")
    manifest = state.load_manifest()
    manifest.status = TaskStatus.SUCCEEDED
    manifest.completed_tasks = ["T-RETRIEVE"]
    state.save_manifest(manifest)
    with pytest.raises(PlanImportError) as excinfo:
        import_plan_into_run(
            state, plan, contract, source="manual", review_approved=False
        )
    assert excinfo.value.exit_code == 4
    assert "re-import forbidden" in str(excinfo.value)
