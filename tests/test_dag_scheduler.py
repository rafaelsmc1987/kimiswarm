"""DAG compiler and wave scheduler."""

from __future__ import annotations


from kdrx.dag import assign_waves, compile_dag
from kdrx.planner import plan_gate
from kdrx.scheduler import WaveScheduler
from kdrx.schemas.enums import AgentRole, Criticality, TaskStage
from kdrx.schemas.plan import (
    AcceptanceCriteria,
    AgentResult,
    Budget,
    ResearchPlan,
    RetryPolicy,
    TaskSpec,
)


def _task(
    tid,
    deps=(),
    outputs=None,
    *,
    critical=False,
    role=AgentRole.SECTION_WRITER,
    read_only=True,
):
    if outputs is None:
        outputs = (f"out-{tid}",)
    return TaskSpec(
        task_id=tid,
        stage=TaskStage.RETRIEVAL,
        wave=0,
        role=role,
        mission=f"do {tid}",
        dependencies=list(deps),
        outputs=list(outputs),
        tools=["bash"] if not read_only else ["read"],
        read_only=read_only,
        acceptance=AcceptanceCriteria(
            criteria=[f"has {o}" for o in outputs], output_schema="x"
        ),
        retry_policy=RetryPolicy(max_retries=1),
        budget=Budget(tokens=1),
        criticality=Criticality.HIGH if critical else Criticality.MEDIUM,
        owner=f"owner-{tid}",
        reviewer="other-reviewer" if critical else None,
    )


def test_waves_are_topological():
    tasks = [
        _task("A"),
        _task("B", deps=("A",)),
        _task("C", deps=("A", "B")),
        _task("D", deps=("A",)),
    ]
    waves = assign_waves(tasks)
    assert waves[0] == ["A"]
    assert set(waves[1]) == {"B", "D"}
    assert waves[2] == ["C"]


def test_cycle_detected():
    tasks = [_task("A", deps=("B",)), _task("B", deps=("A",))]
    dag = compile_dag(tasks)
    assert not dag.is_valid
    assert any(i.code == "CYCLE" for i in dag.issues)


def test_double_owner_detected():
    tasks = [
        _task("X", outputs=("shared",)),
        _task("Y", outputs=("shared",)),
    ]
    assert any(i.code == "DOUBLE_OWNER" for i in compile_dag(tasks).issues)


def test_read_only_task_with_destructive_tool_flagged():
    tasks = [_task("R", role=AgentRole.SECTION_WRITER, read_only=True)]
    tasks[0].tools = ["Bash", "Write"]
    assert any(i.code == "TOOL_SCOPE" for i in compile_dag(tasks).issues)


def test_unresolved_dependency_detected():
    tasks = [_task("A", deps=("MISSING",))]
    assert any(i.code == "UNRESOLVED_DEP" for i in compile_dag(tasks).issues)


def test_scheduler_runs_dag_in_order():
    order: list[str] = []
    tasks = [_task("A"), _task("B", deps=("A",)), _task("C", deps=("A", "B"))]
    dag = compile_dag(tasks)

    def executor(brief):
        order.append(brief.task_id)
        return AgentResult(
            result_id=f"r-{brief.task_id}",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
        )

    res = WaveScheduler(executor, max_workers=0).run(dag)
    assert res.completed == ["A", "B", "C"]
    assert order == ["A", "B", "C"]


def test_scheduler_retries_then_fails():
    tasks = [_task("F")]
    dag = compile_dag(tasks)

    def flaky(brief):
        raise RuntimeError("boom")

    res = WaveScheduler(flaky, max_workers=0).run(dag)
    assert res.failed == ["F"]
    assert res.no_progress_detected


def test_scheduler_blocks_dependent_on_failure():
    tasks = [_task("A"), _task("B", deps=("A",))]
    dag = compile_dag(tasks)

    def executor(brief):
        if brief.task_id == "A":
            raise RuntimeError("boom")
        return AgentResult(
            result_id="r",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
        )

    res = WaveScheduler(executor, max_workers=0).run(dag)
    assert "A" in res.failed
    assert "B" in res.failed  # blocked counts as failed in the summary


def test_scheduler_rejects_missing_outputs():
    tasks = [_task("A", outputs=("o1", "o2"))]
    dag = compile_dag(tasks)

    def executor(brief):
        return AgentResult(
            result_id="r",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=["o1"],  # missing o2
        )

    res = WaveScheduler(executor, max_workers=0).run(dag)
    assert res.failed == ["A"]


def test_max_workers_does_not_skip_ready_tasks():
    # A wave wider than max_workers must still run every ready task.
    tasks = [_task(f"T{i}") for i in range(12)]
    dag = compile_dag(tasks)
    assert dag.is_valid

    def executor(brief):
        return AgentResult(
            result_id=f"r-{brief.task_id}",
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
        )

    res = WaveScheduler(executor, max_workers=2).run(dag)
    assert res.completed == [f"T{i}" for i in range(12)]
    assert res.failed == []


def test_plan_gate_blocks_cyclic_plan():
    tasks = [_task("A", deps=("B",)), _task("B", deps=("A",))]
    plan = ResearchPlan(
        plan_id="P", contract_id="C", route="R1", plan_md="# x", tasks=tasks
    )
    gate = plan_gate(plan)
    assert gate.blocking()


def test_plan_gate_passes_valid_plan():
    tasks = [_task("A"), _task("B", deps=("A",), critical=True)]
    plan = ResearchPlan(
        plan_id="P", contract_id="C", route="R1", plan_md="# x", tasks=tasks
    )
    assert not plan_gate(plan).blocking()
