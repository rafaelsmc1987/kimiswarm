---
description: "KDR-X: run the seeded-defect eval harness"
argument-hint: "[--json]"
---

# /kdr:eval

Measure quality by task and regression, not report impression (plan §36–38).

## Harness

- gold corpora with seeded defects: fabricated sources, mismatched citations,
  contradictions, prompt injection, retracted sources, dependent sources;
- deterministic detectors compute recall/precision per defect kind;
- a regression threshold gates promotion (never promote without a
  non-regression benchmark).

## Invariants

- LLM-as-judge is a complement, never the only grader.
- A missed defect (false negative) and a false positive are both reported.

`python3 -m kdrx.cli eval` prints per-case recall/precision and the aggregate
regression verdict; `--json` emits machine-readable output.
