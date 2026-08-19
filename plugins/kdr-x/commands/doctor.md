---
description: "KDR-X: self-check schemas, scheduler and gates"
argument-hint: ""
---

# /kdr:doctor

Verify the deterministic core is healthy before trusting a run.

## Checks

- all 15 canonical schemas import and round-trip;
- the DAG compiler rejects cycles, double ownership and self-review;
- the wave scheduler completes a trivial DAG and reports failures;
- the eval harness passes its built-in seeded-defect suite;
- JSON schema export succeeds.

`kdr doctor` runs the smoke check; `kdr eval`
runs the seeded-defect regression suite.

