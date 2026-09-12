"""Behavioral regressions from .plano, recorded red against the audited SHA."""

import json

import pytest

from kdrx.adapters import CrossrefAdapter, OpenAlexAdapter
from kdrx.claims import entailment_score
from kdrx.corpus import canonicalize_url
from kdrx.dag import compile_dag
from kdrx.reporting import citation_integrity_gate, extract_citations
from kdrx.retrieval import FileCorpus
from kdrx.runner import (
    _FileResearchExecutor,
    build_contract,
    build_plan,
    execute_plan,
    prepare_run_dir,
    resume_run,
)
from kdrx.scheduler import ExecutorError, WaveScheduler, _brief_for
from kdrx.schemas.plan import AgentResult
from kdrx.state import RunState, hash_file, run_id_from_plan


def started(tmp_path):
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "study.txt").write_text(
        "The model improves accuracy by 12 percent.\n"
        + "Background information. " * 90
        + "\nLatency is 5 ms under load.\n",
        encoding="utf-8",
    )
    contract = build_contract("model accuracy and latency")
    plan = build_plan(contract, 1)
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    return FileCorpus(folder), plan, contract, state


def test_run_ids_do_not_collide():
    assert len({run_id_from_plan("same") for _ in range(1000)}) == 1000


@pytest.mark.parametrize(
    "run_id", ["../x", "../../x", "/x", "C:\\x", "a/b", "a\\b", "..", "CON", "x."]
)
def test_run_id_rejects_unsafe_components(tmp_path, run_id):
    with pytest.raises(ValueError):
        RunState(tmp_path, run_id)
    assert not list(tmp_path.iterdir())


def test_scaffold_is_exclusive(tmp_path):
    _, plan, contract, state = started(tmp_path)
    old = state.manifest_path.read_bytes()
    with pytest.raises(FileExistsError):
        prepare_run_dir(plan, contract, state.root, state.run_id)
    assert state.manifest_path.read_bytes() == old


def test_scheduler_rejects_other_task():
    task = build_plan(build_contract("test")).tasks[0]
    outcome = AgentResult(
        result_id="r",
        task_id="other",
        agent_role=task.role,
        outputs_produced=task.outputs,
    )
    with pytest.raises(ExecutorError, match="identity"):
        WaveScheduler._validate_outcome(task, outcome)


@pytest.mark.parametrize(
    "sid",
    ["file:sub dir/ação.txt", "https://example.org/a?q=x&ref=v1", "doi:10.1234/abc"],
)
def test_citations_round_trip_legacy_ids(sid):
    assert extract_citations(f"Evidence [cite:{sid}]") == [sid]


def test_empty_report_fails():
    assert citation_integrity_gate("", sources=[], claims=[], spans=[]).blocking()


def test_malformed_citation_fails():
    assert citation_integrity_gate(
        "Claim [cite: ]", sources=[], claims=[], spans=[]
    ).blocking()


def test_negation_does_not_support_claim():
    assert (
        entailment_score("The treatment is effective", "The treatment is not effective")
        == 0
    )


def test_openalex_nullable_source():
    adapter = OpenAlexAdapter(
        transport=lambda *_: json.dumps(
            {
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "title": "Study",
                        "primary_location": {"source": None},
                    }
                ]
            }
        )
    )
    assert adapter.search("study")[0].publisher is None


def test_crossref_preserves_full_date():
    adapter = CrossrefAdapter(
        transport=lambda *_: json.dumps(
            {"message": {"title": ["Study"], "issued": {"date-parts": [[2026, 7, 23]]}}}
        )
    )
    assert (
        adapter.lookup_doi("10.1234/example").date.isoformat().startswith("2026-07-23")
    )


def test_semantic_url_parameters_are_not_dropped():
    assert canonicalize_url("https://example.org/code?ref=v1") != canonicalize_url(
        "https://example.org/code?ref=v2"
    )


def test_deep_dag_does_not_recurse():
    template = build_plan(build_contract("test")).tasks[1]
    tasks = [
        template.model_copy(
            update={
                "task_id": str(i),
                "dependencies": [str(i + 1)] if i < 1499 else [],
                "outputs": [f"out/{i}.json"],
            }
        )
        for i in range(1500)
    ]
    assert compile_dag(tasks).is_valid


def test_claims_use_exact_distinct_spans(tmp_path):
    corpus, plan, contract, state = started(tmp_path)
    executor = _FileResearchExecutor(corpus, state, contract.objective)
    executor(_brief_for(plan.tasks[0]))
    spans = {span.evidence_id: span for span in executor.spans}
    for claim in executor.claims:
        assert claim.support_edges
        assert any(
            claim.statement in spans[ref].verbatim_span for ref in claim.support_edges
        )
    first = next(c for c in executor.claims if "12 percent" in c.statement)
    last = next(c for c in executor.claims if "5 ms" in c.statement)
    assert first.support_edges != last.support_edges


def test_partial_resume_in_fresh_process(tmp_path):
    import subprocess
    import sys

    corpus, plan, contract, state = started(tmp_path)
    script = (
        "import sys; from pathlib import Path; from kdrx.runner import *; "
        "from kdrx.retrieval import FileCorpus; from kdrx.state import RunState; "
        "s=RunState(Path(sys.argv[1]).parent,Path(sys.argv[1]).name); "
        "p=ResearchPlan.model_validate_json(s.read_text('plan.json')); "
        "c=ResearchContract.model_validate_json(s.read_text('research_contract.json')); "
        "original=s.append_event; "
        "s.append_event=lambda e: (original(e), (_ for _ in ()).throw(KeyboardInterrupt()) "
        "if e.get('kind')=='task_started' and e.get('task_id')=='T-VERIFY' else None); "
        "execute_plan(p,c,FileCorpus(sys.argv[2]),s)"
    )
    process = subprocess.run(
        [sys.executable, "-c", script, str(state.run_dir), str(tmp_path / "corpus")],
        capture_output=True,
    )
    assert process.returncode != 0
    assert state.load_manifest().completed_tasks == ["T-RETRIEVE"]
    result, executor = resume_run(RunState(state.root, state.run_id), corpus)
    assert not result.failed
    assert executor.sources and executor.claims
    assert [e["task_id"] for e in result.events if e["kind"] == "task_started"].count(
        "T-RETRIEVE"
    ) == 0


def test_resume_rejects_tampered_artifact(tmp_path):
    corpus, plan, contract, state = started(tmp_path)
    result, _ = execute_plan(plan, contract, corpus, state)
    assert not result.failed
    state.write_text("evidence/spans.jsonl", "{}\n")
    with pytest.raises(ValueError, match="hash|integrity"):
        resume_run(RunState(state.root, state.run_id), corpus)


def test_execute_rejects_plan_drift(tmp_path):
    corpus, plan, contract, state = started(tmp_path)
    plan.tasks[0].mission = "Different task"
    with pytest.raises(ValueError, match="plan"):
        execute_plan(plan, contract, corpus, state)


def test_missing_outputs_do_not_commit(tmp_path, monkeypatch):
    corpus, plan, contract, state = started(tmp_path)

    def invented(self, brief):
        return AgentResult(
            result_id="fake",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
        )

    monkeypatch.setattr(_FileResearchExecutor, "__call__", invented)
    result, _ = execute_plan(plan, contract, corpus, state)
    assert not result.completed
    assert state.load_manifest().completed_tasks == []


def test_report_hash_is_frozen_at_verification(tmp_path, monkeypatch):
    from kdrx.cli import main
    import kdrx.runner as runner

    corpus, plan, contract, state = started(tmp_path)
    execute_plan(plan, contract, corpus, state)
    verified = hash_file(state.run_dir / "delivery/report.md")
    original = runner.seal_delivery

    def mutate(*args, **kwargs):
        state.write_text("delivery/report.md", "Invented content never verified.\n")
        return original(*args, **kwargs)

    monkeypatch.setattr(runner, "seal_delivery", mutate)
    code = main(["seal", "--run-dir", str(state.run_dir), "--json"])
    delivery = json.loads(state.read_text("delivery-manifest.json"))
    assert code != 0 or delivery["verified_report_hash"] == verified
