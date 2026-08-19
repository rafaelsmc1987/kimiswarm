"""Deterministic DAG compiler (plan §15).

The compiler turns a list of :class:`TaskSpec` into a validated DAG with
topological waves. It enforces every check listed in §15 deterministically so
that a malformed plan cannot reach the scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from kdrx.schemas.plan import OwnershipEntry, TaskSpec
from kdrx.schemas.enums import Criticality

# Tool names that a read-only research worker must never receive.
DESTRUCTIVE_TOOL_MARKERS = (
    "rm",
    "delete",
    "write",
    "edit",
    "bash",
    "exec",
    "shell",
    "git push",
    "drop",
    "truncate",
)


class DAGValidationError(Exception):
    """Raised when a plan violates a structural invariant."""


@dataclass
class DAGIssue:
    """A single structural problem found during compilation."""

    code: str
    message: str
    task_ids: list[str] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - trivial
        scope = f" [{', '.join(self.task_ids)}]" if self.task_ids else ""
        return f"{self.code}: {self.message}{scope}"


@dataclass
class CompiledDAG:
    """The validated output of the compiler."""

    tasks: list[TaskSpec]
    waves: dict[int, list[str]]
    ownership: list[OwnershipEntry]
    issues: list[DAGIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues

    @property
    def max_wave(self) -> int:
        return max(self.waves) if self.waves else 0

    def task_by_id(self, task_id: str) -> TaskSpec | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def topological_task_ids(self) -> list[str]:
        """Task ids ordered by wave, then insertion order (stable)."""
        out: list[str] = []
        for wave in range(0, self.max_wave + 1):
            out.extend(self.waves.get(wave, []))
        return out


def _detect_cycle(tasks: list[TaskSpec]) -> list[str]:
    """Return the ids on a cycle if one exists, else an empty list.

    Uses iterative DFS with three-color marking (Kahn-free, so it can report
    the offending cycle members).
    """
    by_id = {t.task_id: t for t in tasks}
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {t.task_id: WHITE for t in tasks}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for dep in by_id[node].dependencies:
            if dep not in by_id:
                continue  # unresolved dep is reported separately
            if color[dep] == GRAY:
                # cycle: dep ... node ... dep
                idx = stack.index(dep)
                return stack[idx:] + [dep]
            if color[dep] == WHITE:
                found = dfs(dep)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for t in tasks:
        if color[t.task_id] == WHITE:
            found = dfs(t.task_id)
            if found:
                return found
    return []


def assign_waves(tasks: Iterable[TaskSpec]) -> dict[int, list[str]]:
    """Compute waves so that every task runs after all its dependencies.

    wave(task) = 1 + max(wave(dep) for dep in dependencies), with wave 0 for
    tasks that have no dependencies. Ties preserve insertion order.
    """
    tasks = list(tasks)
    by_id = {t.task_id: t for t in tasks}
    wave_of: dict[str, int] = {}

    def resolve(task_id: str, visiting: set[str]) -> int:
        if task_id in wave_of:
            return wave_of[task_id]
        if task_id in visiting:
            # Cycle guard: a cycle is already reported by the compiler; return a
            # large number so callers get a stable (if meaningless) ordering.
            return 0
        visiting.add(task_id)
        task = by_id.get(task_id)
        deps = task.dependencies if task else []
        w = 0
        for dep in deps:
            if dep in by_id:
                w = max(w, resolve(dep, visiting))
        visiting.remove(task_id)
        wave_of[task_id] = w + 1 if deps else 0
        return wave_of[task_id]

    for t in tasks:
        resolve(t.task_id, set())

    waves: dict[int, list[str]] = {}
    for t in tasks:
        waves.setdefault(wave_of[t.task_id], []).append(t.task_id)
    return dict(sorted(waves.items()))


def compile_dag(tasks: list[TaskSpec]) -> CompiledDAG:
    """Validate a task list and produce a :class:`CompiledDAG`.

    Runs every §15 check. Returns the compiled DAG even when invalid so callers
    can render all issues at once; use ``.is_valid`` / ``.issues`` to decide.
    """
    issues: list[DAGIssue] = []
    by_id = {t.task_id: t for t in tasks}

    # Duplicate ids
    seen: set[str] = set()
    for t in tasks:
        if t.task_id in seen:
            issues.append(
                DAGIssue("DUP_ID", f"duplicate task id {t.task_id}", [t.task_id])
            )
        seen.add(t.task_id)

    # Missing mission / dependencies resolve
    for t in tasks:
        if not t.mission.strip():
            issues.append(DAGIssue("NO_MISSION", "task has no mission", [t.task_id]))
        for dep in t.dependencies:
            if dep not in by_id:
                issues.append(
                    DAGIssue(
                        "UNRESOLVED_DEP",
                        f"dependency '{dep}' does not resolve",
                        [t.task_id],
                    )
                )

    # Acyclic
    cycle = _detect_cycle(tasks)
    if cycle:
        issues.append(DAGIssue("CYCLE", "dependency cycle detected", cycle))

    # One owner per output
    output_owner: dict[str, str] = {}
    for t in tasks:
        for out in t.outputs:
            if out in output_owner:
                issues.append(
                    DAGIssue(
                        "DOUBLE_OWNER",
                        f"output '{out}' produced by both {output_owner[out]} and {t.task_id}",
                        [output_owner[out], t.task_id],
                    )
                )
            else:
                output_owner[out] = t.task_id

    # Output schema present (acceptance.output_schema or explicit outputs)
    for t in tasks:
        if not t.outputs:
            issues.append(
                DAGIssue("NO_OUTPUTS", "task declares no outputs", [t.task_id])
            )
        elif not t.acceptance.output_schema and not t.acceptance.criteria:
            issues.append(
                DAGIssue(
                    "NO_SCHEMA",
                    "task has outputs but no acceptance schema or criteria",
                    [t.task_id],
                )
            )

    # Reviewer != author
    for t in tasks:
        if t.owner and t.reviewer and t.owner == t.reviewer:
            issues.append(
                DAGIssue("SELF_REVIEW", "reviewer must differ from owner", [t.task_id])
            )

    # Verifier for critical claims
    for t in tasks:
        if t.criticality == Criticality.HIGH and not t.reviewer:
            issues.append(
                DAGIssue(
                    "NO_VERIFIER",
                    "critical task must have an independent reviewer",
                    [t.task_id],
                )
            )

    # Budget valid
    for t in tasks:
        if t.budget.tokens < 0 or t.budget.queries < 0 or t.budget.wall_seconds < 0:
            issues.append(
                DAGIssue(
                    "BAD_BUDGET", "budget values must be non-negative", [t.task_id]
                )
            )

    # Minimal tool scope: read-only workers must not hold destructive tools
    for t in tasks:
        if t.read_only:
            destructive = [
                tool
                for tool in t.tools
                if any(marker in tool.lower() for marker in DESTRUCTIVE_TOOL_MARKERS)
            ]
            if destructive:
                issues.append(
                    DAGIssue(
                        "TOOL_SCOPE",
                        f"read-only task declares destructive tools {destructive}",
                        [t.task_id],
                    )
                )

    # Same-wave dependency (only meaningful once waves are computed)
    waves = assign_waves(tasks)
    wave_of = {tid: w for w, ids in waves.items() for tid in ids}
    for t in tasks:
        for dep in t.dependencies:
            if dep in wave_of and wave_of[dep] >= wave_of[t.task_id]:
                issues.append(
                    DAGIssue(
                        "SAME_WAVE_DEP",
                        f"task depends on '{dep}' in the same or later wave",
                        [t.task_id, dep],
                    )
                )

    ownership = [
        OwnershipEntry(output=out, owner_task_id=owner, owner_role=by_id[owner].role)
        for out, owner in output_owner.items()
    ]

    return CompiledDAG(tasks=tasks, waves=waves, ownership=ownership, issues=issues)
