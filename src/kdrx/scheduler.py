"""Deterministic wave scheduler (plan §16).

The scheduler is the only component allowed to launch agents. It walks the
compiled DAG wave by wave, enforces the ownership registry, applies retry and
no-progress policies, and emits an append-only event stream. The executor is
injected so the scheduler is fully testable without a live model.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable

from kdrx.dag import CompiledDAG
from kdrx.schemas.enums import TaskStatus
from kdrx.schemas.plan import AgentBrief, AgentResult, TaskSpec

AgentExecutor = Callable[[AgentBrief], AgentResult]
EventSink = Callable[[dict], None]


class ExecutorError(Exception):
    """Raised when an injected executor cannot produce a result."""


@dataclass
class TaskState:
    task: TaskSpec
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    result: AgentResult | None = None


@dataclass
class ScheduleResult:
    """Summary of one scheduler run."""

    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    no_progress_detected: bool = False

    @property
    def succeeded_all(self) -> bool:
        return not self.failed and bool(self.completed)


def _brief_for(task: TaskSpec) -> AgentBrief:
    return AgentBrief(
        brief_id=f"BR-{task.task_id}",
        task_id=task.task_id,
        role=task.role,
        mission=task.mission,
        inputs=task.inputs,
        outputs=task.outputs,
        skills=task.skills,
        tools=task.tools,
        read_only=task.read_only,
        source_policy=task.source_policy,
        acceptance=task.acceptance,
    )


class WaveScheduler:
    """Runs a :class:`CompiledDAG` to completion, wave by wave.

    Parameters
    ----------
    executor:
        Function that turns an :class:`AgentBrief` into an :class:`AgentResult`.
    emit:
        Optional event sink; receives one dict per lifecycle event.
    max_workers:
        Upper bound on concurrent agents per wave (the scheduler itself is
        sequential and deterministic; this only bounds how many it *would*
        dispatch, surfaced for observability and backpressure).
    """

    def __init__(
        self,
        executor: AgentExecutor,
        emit: EventSink | None = None,
        max_workers: int = 8,
    ) -> None:
        self.executor = executor
        self.emit = emit or (lambda _e: None)
        self.max_workers = max_workers
        self._seq = itertools.count(1)
        self._events: list[dict] = []

    def _event(self, kind: str, **payload: object) -> dict:
        return {"seq": next(self._seq), "kind": kind, **payload}

    def _emit(self, event: dict) -> None:
        """Record an event locally and forward it to the sink."""
        self._events.append(event)
        self.emit(event)

    def run(self, dag: CompiledDAG) -> ScheduleResult:
        """Execute every task in topological wave order.

        A wave is considered done only when all of its tasks have either
        succeeded or exhausted their retry policy. The result records the final
        status of every task so callers can drive the Stop gate.
        """
        if not dag.is_valid:
            raise ValueError("cannot schedule an invalid DAG (issues present)")

        states: dict[str, TaskState] = {t.task_id: TaskState(task=t) for t in dag.tasks}
        result = ScheduleResult()

        for wave in range(0, dag.max_wave + 1):
            wave_ids = dag.waves.get(wave, [])
            self._run_wave(wave, wave_ids, states, result)

        result.completed = [
            tid for tid, s in states.items() if s.status == TaskStatus.SUCCEEDED
        ]
        result.failed = [
            tid
            for tid, s in states.items()
            if s.status in (TaskStatus.FAILED, TaskStatus.BLOCKED)
        ]
        result.events = self._events
        return result

    def _dependencies_satisfied(
        self, task: TaskSpec, states: dict[str, TaskState]
    ) -> bool:
        return all(
            states.get(dep) is not None and states[dep].status == TaskStatus.SUCCEEDED
            for dep in task.dependencies
        )

    def _run_wave(
        self,
        wave: int,
        wave_ids: list[str],
        states: dict[str, TaskState],
        result: ScheduleResult,
    ) -> None:
        ready = [
            tid
            for tid in wave_ids
            if states[tid].status == TaskStatus.PENDING
            and self._dependencies_satisfied(states[tid].task, states)
        ]

        # Sequential deterministic pass over every ready task. ``max_workers`` is
        # a documented concurrency bound for a future parallel executor; it must
        # NOT skip ready tasks in the sequential path (a skipped task would be
        # wrongly marked BLOCKED below).
        for tid in ready:
            self._run_task(tid, states, result)

        # Any task still PENDING here had unsatisfied dependencies (ready tasks
        # were filtered out); mark it BLOCKED rather than silently skipping it.
        for tid in wave_ids:
            st = states[tid]
            if st.status == TaskStatus.PENDING:
                unsatisfied = [
                    dep
                    for dep in st.task.dependencies
                    if states.get(dep) is None
                    or states[dep].status not in (TaskStatus.SUCCEEDED,)
                ]
                st.status = TaskStatus.BLOCKED
                st.last_error = f"blocked by failed/unsatisfied deps: {unsatisfied}"
                self._emit(self._event("task_blocked", task_id=tid, deps=unsatisfied))

    def _run_task(
        self,
        tid: str,
        states: dict[str, TaskState],
        result: ScheduleResult,
    ) -> None:
        st = states[tid]
        task = st.task
        max_attempts = task.retry_policy.max_retries + 1
        no_progress = False

        while st.attempts < max_attempts:
            st.attempts += 1
            st.status = TaskStatus.RUNNING
            self._emit(
                self._event(
                    "task_started",
                    task_id=tid,
                    attempt=st.attempts,
                    role=task.role.value,
                )
            )
            try:
                brief = _brief_for(task)
                outcome = self.executor(brief)
                self._validate_outcome(task, outcome)
                st.result = outcome
                st.status = TaskStatus.SUCCEEDED
                self._emit(
                    self._event(
                        "task_succeeded",
                        task_id=tid,
                        attempt=st.attempts,
                        outputs=outcome.outputs_produced,
                    )
                )
                return
            except Exception as exc:  # noqa: BLE001 - boundary for untrusted executor
                st.last_error = f"{type(exc).__name__}: {exc}"
                st.status = TaskStatus.RETRYING
                self._emit(
                    self._event(
                        "task_failed",
                        task_id=tid,
                        attempt=st.attempts,
                        error=st.last_error,
                    )
                )
                no_progress = True

        st.status = TaskStatus.FAILED
        result.no_progress_detected = result.no_progress_detected or no_progress
        self._emit(self._event("task_exhausted", task_id=tid, attempts=st.attempts))

    @staticmethod
    def _validate_outcome(task: TaskSpec, outcome: AgentResult | None) -> None:
        # T-02-06: um executor que retorna null é uma falha determinística,
        # não um AttributeError anônimo achatado pelo retry loop.
        if outcome is None:
            raise ExecutorError("executor returned null result")
        if not outcome.covers_outputs(task.outputs):
            missing = set(task.outputs) - set(outcome.outputs_produced)
            raise ExecutorError(f"agent did not produce outputs {sorted(missing)}")
        if task.acceptance.required_evidence_refs:
            if len(outcome.evidence_refs) < task.acceptance.required_evidence_refs:
                raise ExecutorError(
                    f"agent produced {len(outcome.evidence_refs)} evidence refs, "
                    f"need >= {task.acceptance.required_evidence_refs}"
                )
