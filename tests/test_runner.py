"""End-to-end offline pipeline (routes R3/R4)."""

from __future__ import annotations

import json

from kdrx.runner import run_file_research


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
