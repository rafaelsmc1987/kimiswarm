import threading
import time

from kdrx.dag import compile_dag
from kdrx.scheduler import WaveScheduler
from kdrx.schemas.enums import AgentRole, TaskStage
from kdrx.schemas.plan import AcceptanceCriteria, AgentResult, RetryPolicy, TaskSpec


def task(tid, deps=()):
    return TaskSpec(
        task_id=tid,
        stage=TaskStage.RETRIEVAL,
        wave=0,
        role=AgentRole.WEB_EXPLORER,
        mission=tid,
        outputs=[f"{tid}.txt"],
        dependencies=list(deps),
        acceptance=AcceptanceCriteria(criteria=["exists"]),
        retry_policy=RetryPolicy(max_retries=0),
    )


def test_four_workers_overlap_without_fifth():
    lock = threading.Lock()
    active = peak = 0
    barrier = threading.Barrier(4)

    def executor(brief):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=5)
        time.sleep(0.01)
        with lock:
            active -= 1
        return AgentResult(
            result_id=brief.task_id,
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
        )

    result = WaveScheduler(executor, max_workers=4).run(
        compile_dag([task(str(i)) for i in range(8)])
    )
    assert peak == 4 and not result.failed


def test_descendant_does_not_wait_for_unrelated_sibling():
    descendant = threading.Event()

    def executor(brief):
        if brief.task_id == "slow":
            assert descendant.wait(5), "wave barrier prevented ready descendant"
        elif brief.task_id == "child":
            descendant.set()
        elif brief.task_id == "bad":
            raise RuntimeError("isolated branch failure")
        return AgentResult(
            result_id=brief.task_id,
            task_id=brief.task_id,
            agent_role=brief.role,
            outputs_produced=brief.outputs,
        )

    result = WaveScheduler(executor, max_workers=4).run(
        compile_dag(
            [
                task("fast"),
                task("slow"),
                task("child", ["fast"]),
                task("bad"),
                task("blocked", ["bad"]),
            ]
        )
    )
    assert set(result.completed) == {"fast", "slow", "child"}
    assert set(result.failed) == {"bad", "blocked"}
