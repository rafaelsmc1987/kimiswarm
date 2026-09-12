import pytest

from kdrx.planner import plan_gate
from kdrx.retrieval import FileCorpus
from kdrx.runner import build_contract, build_plan, execute_plan, prepare_run_dir
from kdrx.schemas.enums import AgentRole


def test_arbitrary_task_ids_and_additional_registered_capabilities_execute(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "study.txt").write_text("Latency is 5 ms under load.", encoding="utf-8")
    contract = build_contract("latency under load")
    plan = build_plan(contract)
    names = {task.task_id: f"custom-{i}" for i, task in enumerate(plan.tasks)}
    for task in plan.tasks:
        task.task_id = names[task.task_id]
        task.dependencies = [names[d] for d in task.dependencies]
    plan.tasks.append(
        plan.tasks[1].model_copy(
            update={
                "task_id": "assess-claims",
                "kind": "claim_analysis",
                "outputs": ["analysis/assessment.json"],
                "role": AgentRole.COMPARATIVE_ANALYST,
                "owner": "claims-analyst",
            }
        )
    )
    plan.tasks.append(
        plan.tasks[1].model_copy(
            update={
                "task_id": "export-evidence",
                "kind": "artifact_export",
                "outputs": ["delivery/evidence-pack.json"],
                "role": AgentRole.ARTIFACT_CONVERTER,
                "owner": "exporter",
            }
        )
    )
    assert not plan_gate(plan, contract).blocking()
    state, _ = prepare_run_dir(plan, contract, tmp_path / "runs")
    result, _ = execute_plan(plan, contract, FileCorpus(corpus), state)
    assert result.deliverable and len(result.completed) == 6
    assert state._resolve("delivery/evidence-pack.json").is_file()


def test_missing_capability_blocks_planning_before_writing(tmp_path):
    contract = build_contract("objective")
    plan = build_plan(contract)
    plan.tasks[0].kind = "nonexistent-provider-capability"
    gate = plan_gate(plan, contract)
    assert gate.blocking()
    assert any(
        check.check_id == "CAPABILITIES_AVAILABLE" and not check.passed
        for check in gate.checks
    )
    with pytest.raises(ValueError, match="set task.kind"):
        prepare_run_dir(plan, contract, tmp_path / "runs")
    assert not (tmp_path / "runs").exists()


def test_code_and_implicit_model_execution_do_not_fall_back_to_fixtures():
    from kdrx.runtime.executors import EXECUTORS

    contract = build_contract("objective")
    plan = build_plan(contract)
    plan.tasks[0].kind = "code"
    assert "sandbox" in EXECUTORS.issues(plan)[0]
    plan.tasks[0].kind = "model_analysis"
    assert "explicit codex or claude-code" in EXECUTORS.issues(plan)[0]


@pytest.mark.parametrize(
    "first,second",
    [
        ("a/../b.json", "b.json"),
        ("a/b.json", "a\\b.json"),
        ("B.json", "b.json"),
        ("b.json.", "b.json"),
        ("NUL.json", "safe.json"),
        ("x:stream", "x"),
        ("root", "root/file.json"),
    ],
)
def test_equivalent_output_paths_block_before_scaffolding(tmp_path, first, second):
    contract = build_contract("objective")
    plan = build_plan(contract)
    plan.tasks[0].outputs = [first]
    plan.tasks[1].outputs = [second]
    with pytest.raises(ValueError, match="invalid plan DAG"):
        prepare_run_dir(plan, contract, tmp_path / "runs")


@pytest.mark.parametrize(
    "path",
    [
        "manifest.json",
        "EVENTS.JSONL",
        "plan.json",
        "history/plan-patches/1.json",
        "delivery/revisions/old.md",
        "tasks",
        "tasks/T-RETRIEVE/result.json",
        "tasks/T-VERIFY/provider-receipt.json",
        "verification/seal",
    ],
)
def test_task_cannot_own_kernel_control_paths(tmp_path, path):
    contract = build_contract("objective")
    plan = build_plan(contract)
    plan.tasks[0].outputs = [path]
    with pytest.raises(ValueError, match="invalid plan DAG"):
        prepare_run_dir(plan, contract, tmp_path / "runs")
    assert not (tmp_path / "runs").exists()


def test_task_ids_cannot_alias_on_case_insensitive_filesystems(tmp_path):
    contract = build_contract("objective")
    plan = build_plan(contract)
    plan.tasks.append(
        plan.tasks[0].model_copy(
            update={"task_id": "t-retrieve", "outputs": ["other.json"]}
        )
    )
    with pytest.raises(ValueError, match="invalid plan DAG"):
        prepare_run_dir(plan, contract, tmp_path / "runs")
    assert not (tmp_path / "runs").exists()
