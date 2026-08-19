---
description: "KDR-X: re-run source, claim and integrity gates"
argument-hint: "--run-dir <dir>"
---

# /kdr:verify

Re-run the deterministic verification gates over a persisted run, independent
of the original synthesis.

## Gates

- `source_trust_gate` — identity, retraction, COI, currency.
- `claim` standing — recompute from edges and source families.
- `citation_integrity_gate` — citations resolve, material claims have exact
  spans, unsupported sentences flagged, unresolved claims disclosed.
- `security_gate` — secret scan and path safety.

## Invariants

- Verification is re-runnable and deterministic: same inputs, same verdict.
- A gate that fails returns a blocking reason, never a silent pass.

`kdr verify --run-dir <dir>` re-runs the persisted gate
results; use `/kdr:report` to read the assembled output.

