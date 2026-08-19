---
name: claim-graph
description: "Atomic claim decomposition, evidence spans, support/contradict edges, independence and standing (plan §21–24). Use when extracting or verifying claims."
---

# Claim-Evidence Graph

The epistemic core: `atomic claim -> exact evidence span -> source -> standing`.

## Workflow

1. **Decompose** compound statements into atomic `Claim`s
   (`kdrx.claims.decompose_into_claims`).
2. **Extract** exact `EvidenceSpan`s with locators (`kdrx.schemas.corpus`).
3. **Classify** edges: SUPPORTS / PARTIALLY_SUPPORTS / CONTRADICTS / QUALIFIES /
   CONTEXT_ONLY / IRRELEVANT / CANNOT_DETERMINE.
4. **Compute standing** with `kdrx.claims.compute_standing` — a transparent
   function of direct support, quality, independence, scope match, recency,
   contradiction strength, methodological consistency, extraction confidence.
5. **Calibrate** — confidence is derived, never an adjective.

## Rule

Five news articles copying one press release are one family
(`kdrx.corpus.independence_families`). Source count is not evidence strength.
