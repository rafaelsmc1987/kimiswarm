---
description: "KDR-X: execute an approved plan via the wave scheduler"
argument-hint: "[--run-dir <dir>]"
---

# /kdr:run

Execute an approved plan. Never start research without a plan gate that passed.

## Steps

1. Load the `ResearchPlan` and re-validate with `kdrx.planner.plan_gate`.
2. Build the `CompiledDAG` with `kdrx.dag.compile_dag`.
3. Drive `kdrx.scheduler.WaveScheduler` wave by wave:
   - only the scheduler launches agents;
   - respect retry and no-progress policies;
   - emit every lifecycle event to `events.jsonl`.
4. Between waves, run the deterministic gates (`SubagentStop`,
   `TaskCompleted`); a task that fails its acceptance is retried, then blocked.
5. On completion, run the Stop gate (`kdrx.hooks.hook_stop`): DAG closed,
   critical claims resolved or disclosed, integrity pass, secret scan clean,
   delivery manifest present.

## Invariants

- Writers never do the central research; reviewers are independent.
- Every material claim resolves to an exact evidence span.
- Any failure surfaces in `failed_tasks`, never silently.

For the offline file-corpus path, `kdr run --corpus <dir>`
executes the deterministic pipeline end to end.

