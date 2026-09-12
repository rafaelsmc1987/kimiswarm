import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from kdrx.retrieval import FileCorpus
from kdrx.runner import (
    build_contract,
    build_plan,
    execute_plan,
    prepare_run_dir,
    resume_run,
)
from kdrx.runtime.store import StateConflict
from kdrx.schemas.enums import AgentRole
from kdrx.schemas.plan import PlanPatch, ResearchPlan
from kdrx.runtime.plan_revisions import apply_patch


def completed_run(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    contract = build_contract("latency under load")
    plan = build_plan(contract)
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    result, _ = execute_plan(plan, contract, FileCorpus(corpus), state)
    assert result.deliverable
    return state, plan, corpus


def validation_task(plan, task_id="validate-conflict"):
    return plan.tasks[1].model_copy(
        update={
            "task_id": task_id,
            "kind": "claim_analysis",
            "outputs": [f"analysis/{task_id}.json"],
            "role": AgentRole.COMPARATIVE_ANALYST,
            "owner": task_id,
        }
    )


def test_new_validation_preserves_completed_branches_and_original_receipts(tmp_path):
    state, plan, corpus = completed_run(tmp_path)
    original = state.store.completed(state.run_id)
    paths = [state._resolve(f"tasks/{tid}/result.json") for tid in original]
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    result = apply_patch(
        state,
        PlanPatch(
            base_revision=0, reason="new conflict", add_tasks=[validation_task(plan)]
        ),
    )
    assert result["invalidated_tasks"] == []
    assert state.load_manifest().metadata["seal"]["eligible"] is False
    resumed, _ = resume_run(state, FileCorpus(corpus))
    assert resumed.deliverable and len(resumed.completed) == 5
    assert before == [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    assert all(
        state.store.completed(state.run_id)[tid] == r for tid, r in original.items()
    )
    assert (
        state.store.completed(state.run_id)["validate-conflict"]["plan_revision"] == 1
    )


def test_two_patches_on_same_base_require_rebase(tmp_path):
    state, plan, _ = completed_run(tmp_path)

    def propose(i):
        try:
            return apply_patch(
                state,
                PlanPatch(
                    base_revision=0,
                    reason="concurrent review",
                    add_tasks=[validation_task(plan, f"review-{i}")],
                ),
            )
        except StateConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(propose, range(2)))
    assert sum(r is not None for r in results) == 1
    persisted = ResearchPlan.model_validate_json(state.read_text("plan.json"))
    assert persisted.plan_revision == 1 and len(persisted.tasks) == 5
    assert (
        len(
            [e for e in state.store.events(state.run_id) if e["kind"] == "plan_patched"]
        )
        == 1
    )


def test_explicit_damage_invalidation_reexecutes_only_branch(tmp_path):
    state, plan, corpus = completed_run(tmp_path)
    original = state.store.completed(state.run_id)
    task = next(t for t in plan.tasks if t.kind == "synthesis")
    state.write_text("delivery/report.md", "corrupted")
    with pytest.raises(ValueError, match="integrity"):
        resume_run(state, FileCorpus(corpus))
    changed = apply_patch(
        state,
        PlanPatch(
            base_revision=0,
            reason="disk damage in report",
            invalidate_tasks=[task.task_id],
        ),
    )
    assert task.task_id in changed["invalidated_tasks"]
    resumed, _ = resume_run(state, FileCorpus(corpus))
    assert resumed.deliverable
    current = state.store.completed(state.run_id)
    for tid, receipt in original.items():
        assert (receipt == current[tid]) == (tid not in changed["invalidated_tasks"])
    assert "corrupted" not in state.read_text("delivery/report.md")


def test_running_task_blocks_patch_and_old_scheduler_cannot_claim(tmp_path):
    contract = build_contract("latency")
    plan = build_plan(contract)
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    state.store.register_tasks(state.run_id, [t.task_id for t in plan.tasks])
    lease = state.store.claim(
        state.run_id, plan.tasks[0].task_id, "worker", expected_revision=0
    )
    patch = PlanPatch(
        base_revision=0, reason="review", add_tasks=[validation_task(plan)]
    )
    with pytest.raises(StateConflict, match="in flight"):
        apply_patch(state, patch)
    state.store.finish(lease, {"error": "stopped"}, [], success=False)
    apply_patch(state, patch)
    with pytest.raises(StateConflict, match="revision"):
        state.store.claim(
            state.run_id, plan.tasks[0].task_id, "stale", expected_revision=0
        )


@pytest.mark.parametrize(
    "change", ["capability", "cycle", "ownership", "completed", "budget"]
)
def test_invalid_patch_leaves_plan_and_receipts_unchanged(tmp_path, change):
    state, plan, _ = completed_run(tmp_path)
    task = validation_task(plan)
    kwargs = {"add_tasks": [task]}
    if change == "capability":
        task.kind = "unavailable"
    elif change == "cycle":
        task.dependencies = [task.task_id]
    elif change == "ownership":
        task.outputs = [plan.tasks[0].outputs[0].upper()]
    elif change == "completed":
        kwargs = {"dependencies": {plan.tasks[1].task_id: []}}
    else:
        kwargs = {"task_budgets": {plan.tasks[0].task_id: {"tokens": 1}}}
    before = state.manifest_path.read_bytes(), state._resolve("plan.json").read_bytes()
    with pytest.raises(ValueError):
        apply_patch(state, PlanPatch(base_revision=0, reason=change, **kwargs))
    assert before == (
        state.manifest_path.read_bytes(),
        state._resolve("plan.json").read_bytes(),
    )


def test_plan_patch_cli_is_available(tmp_path, capsys):
    from kdrx.cli import main

    state, plan, _ = completed_run(tmp_path)
    patch = tmp_path / "patch.json"
    patch.write_text(
        PlanPatch(
            base_revision=0, reason="review", add_tasks=[validation_task(plan)]
        ).model_dump_json(),
        encoding="utf-8",
    )
    assert (
        main(["patch-plan", "--run-dir", str(state.run_dir), "--patch", str(patch)])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["plan_revision"] == 1


def test_retrieval_damage_replays_snapshot_even_if_original_corpus_changes(tmp_path):
    state, plan, corpus = completed_run(tmp_path)
    original = state.read_text("corpus/sources.jsonl")
    (corpus / "study.txt").write_text("Latency is 999 ms under load.", encoding="utf-8")
    state.write_text("corpus/sources.jsonl", "damaged")
    apply_patch(
        state,
        PlanPatch(
            base_revision=0,
            reason="damaged export",
            invalidate_tasks=[plan.tasks[0].task_id],
        ),
    )
    resumed, _ = resume_run(state, FileCorpus(corpus))
    assert resumed.deliverable
    assert state.read_text("corpus/sources.jsonl") == original
    assert "999" not in state.read_text("delivery/report.md")


def test_completed_resume_does_not_build_index_until_search(tmp_path, monkeypatch):
    from kdrx.retrieval import BM25

    state, _, corpus = completed_run(tmp_path)
    fitted = []
    original = BM25.fit

    def fit(self, docs):
        fitted.append(True)
        return original(self, docs)

    monkeypatch.setattr(BM25, "fit", fit)
    result, executor = resume_run(state, FileCorpus(corpus))
    assert result.deliverable and fitted == []
    assert executor.corpus.search("latency")
    assert fitted == [True]
    executor.corpus.search("load")
    assert fitted == [True]


def test_old_lifecycle_event_and_wrong_revision_result_rejected(tmp_path):
    state, plan, _ = completed_run(tmp_path)
    apply_patch(
        state,
        PlanPatch(base_revision=0, reason="review", add_tasks=[validation_task(plan)]),
    )
    before = state.load_manifest()
    with pytest.raises(StateConflict, match="revision"):
        state.store.transition(
            state.run_id,
            {"kind": "task_exhausted", "task_id": "validate-conflict"},
            expected_revision=0,
        )
    assert state.load_manifest() == before
    lease = state.store.claim(
        state.run_id, "validate-conflict", "worker", expected_revision=1
    )
    with pytest.raises(StateConflict, match="identity"):
        state.store.finish(
            lease,
            {
                "run_id": state.run_id,
                "task_id": "validate-conflict",
                "attempt_id": lease["attempt_id"],
                "plan_revision": 0,
            },
            [],
        )


def test_failed_publication_recovers_patch_without_applying_twice(
    tmp_path, monkeypatch
):
    from kdrx.runtime.store import ProjectionError
    from kdrx.state import RunState

    state, plan, _ = completed_run(tmp_path)
    original = state._atomic_write

    def fail(path, content):
        if path.name == "plan.json":
            raise OSError("disk full")
        return original(path, content)

    monkeypatch.setattr(state, "_atomic_write", fail)
    patch = PlanPatch(
        base_revision=0, reason="review", add_tasks=[validation_task(plan)]
    )
    with pytest.raises(ProjectionError):
        apply_patch(state, patch)
    reopened = RunState(state.root, state.run_id)
    assert reopened.load_manifest().plan_revision == 1
    assert (
        ResearchPlan.model_validate_json(reopened.read_text("plan.json")).plan_revision
        == 1
    )
    with pytest.raises(StateConflict, match="rebase"):
        apply_patch(reopened, patch)


def test_nonzero_initial_revision_stays_bound_to_manifest_and_lease(tmp_path):
    contract = build_contract("objective")
    plan = build_plan(contract)
    plan.plan_revision = 7
    state, manifest = prepare_run_dir(plan, contract, tmp_path / "runs")
    assert manifest.plan_revision == 7
    result = apply_patch(
        state,
        PlanPatch(base_revision=7, reason="review", add_tasks=[validation_task(plan)]),
    )
    assert result["plan_revision"] == state.load_manifest().plan_revision == 8
    lease = state.store.claim(
        state.run_id, plan.tasks[0].task_id, "worker", expected_revision=8
    )
    assert lease["plan_revision"] == 8 and lease["plan_hash"] == result["plan_hash"]
