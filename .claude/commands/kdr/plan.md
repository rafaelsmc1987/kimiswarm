---
description: "KDR-X: intake, research contract, planner council, DAG and plan gate"
argument-hint: "<objective>"
---

# /kdr:plan

Produce a plan-first research artifact before any searching happens (DoD: "todo
run complexo cria plano antes de pesquisar").

## Steps

1. **Intake** — capture the objective, decision context, audience, scope,
   languages, time window, source policy and risk level. Ask only for what is
   genuinely ambiguous.
2. **Research contract** — materialize a `ResearchContract` (plan §12). Nothing
   is silently open: scope, prohibited sources, freshness, budget, checkpoints.
3. **Planner council** — run five perspectives in parallel (requirements,
   question/scope, retrieval, methodology, risk/verification), then a plan
   reviewer, a DAG verifier and a plan synthesizer (plan §14).
4. **DAG compile** — build `TaskSpec`s and run `kdrx.dag.compile_dag` (acyclic,
   deps resolve, one owner per output, reviewer != author, verifier on critical
   tasks, minimal tool scope).
5. **Plan gate** — run `kdrx.planner.plan_gate`. If it blocks, fix and re-run.
6. **Persist** — write `plan.md`, `research_contract.yaml`, `dag.json`,
   `waves.json`, `tasks/*.json`, `ownership.json`, `budget.json`,
   `acceptance_matrix.json` into the run directory.

## Invariants

- No task has a dependent in the same wave.
- Every output has exactly one owner.
- Critical claims carry an independent reviewer.
- The plan is a DAG, never an agent launching other agents.

Use `python3 -m kdrx.cli doctor` to confirm the deterministic core is healthy,
then run `/kdr:run` once the plan gate passes.
