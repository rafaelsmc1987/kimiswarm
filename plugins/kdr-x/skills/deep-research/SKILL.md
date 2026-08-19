---
name: deep-research
description: "KDR-X deep research: research contract -> planner council -> DAG -> wave scheduler -> claim-evidence graph -> calibrated report. Use whenever a research task requires verified, provenance-tracked findings."
---

# KDR-X Deep Research

Plan-first, claim-first deep research. Never search before a plan gate passes.

## Pipeline (plan §10–31)

1. **Intake** — objective, decision context, audience, risk.
2. **Contract** — `ResearchContract` (scope, languages, source policy, budget).
3. **Plan** — planner council -> `compile_dag` -> `plan_gate`.
4. **Execute** — `WaveScheduler` runs discovery, evidence, reasoning, production
   and audit roles in topological waves.
5. **Verify** — source trust -> atomic claims -> contradiction/falsification.
6. **Synthesize** — evidence pack -> dependency-aware report.
7. **Deliver** — integrity + security gates -> sealed `DeliveryManifest`.

## Hard rules (DoD §44)

- Every material claim has an exact `EvidenceSpan` and a `Standing`.
- Five syndicated copies of one press release count as one source family.
- Citations must exist *and* entail the claim.
- Writers never do central research; reviewers are independent.
- Any quantitative claim is reproducible (`kdrx.analysis.Calculation`).

## Entry points

`/kdr:plan` -> `/kdr:run` -> `/kdr:report`; `kdr doctor` / `kdr eval` for health.
