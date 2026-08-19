"""Plan gate (plan §14, §33, DoD §44).

The planner council (five parallel perspectives -> review -> DAG verify ->
synthesize) produces a :class:`ResearchPlan`; the *gate* here is deterministic
and decides whether that plan may enter the scheduler. No plan reaches research
before passing this gate.
"""

from __future__ import annotations

from kdrx.dag import CompiledDAG, compile_dag
from kdrx.schemas.enums import Criticality, GateKind
from kdrx.schemas.gate import GateCheck, GateDecision
from kdrx.schemas.plan import ResearchPlan
from kdrx.schemas.request import ResearchContract


def plan_gate(
    plan: ResearchPlan, contract: ResearchContract | None = None
) -> GateDecision:
    """Validate a plan before scheduling.

    Returns a :class:`GateDecision` with ``verdict`` in {pass, warn, fail}.
    A warning does not block; a failure does.
    """
    checks: list[GateCheck] = []

    def check(
        check_id: str, description: str, passed: bool, details: object = None
    ) -> None:
        checks.append(
            GateCheck(
                check_id=check_id,
                description=description,
                passed=passed,
                details=details,
            )
        )

    check(
        "CONTRACT",
        "plan references a non-empty contract id",
        bool(plan.contract_id.strip()),
    )
    if contract is not None:
        check(
            "CONTRACT_MATCH",
            "plan.contract_id matches the supplied contract",
            plan.contract_id == contract.contract_id,
        )
    check("HAS_TASKS", "plan contains at least one task", len(plan.tasks) > 0)
    check("HAS_PLAN_MD", "plan.md text is present", bool(plan.plan_md.strip()))

    dag: CompiledDAG = compile_dag(plan.tasks)
    check(
        "DAG_VALID",
        "DAG compiles with no structural issues",
        dag.is_valid,
        details=[str(i) for i in dag.issues],
    )

    critical = [t for t in plan.tasks if t.criticality == Criticality.HIGH]
    uncovered = [
        t.task_id
        for t in critical
        if not t.acceptance.criteria and not t.acceptance.output_schema
    ]
    check(
        "CRITICAL_ACCEPTANCE",
        "every critical task has acceptance criteria or an output schema",
        not uncovered,
        details=uncovered,
    )

    # Every output must have an owner (compiler already guarantees this; surface
    # the count for observability).
    check(
        "OWNERSHIP",
        "every output has exactly one owner",
        len(dag.ownership) == len({o.output for o in dag.ownership}),
    )

    return GateDecision.compose(
        gate_id="gate:plan",
        kind=GateKind.PLAN,
        checks=checks,
        run_id=plan.plan_id,
        warn_is_pass=False,
    )
