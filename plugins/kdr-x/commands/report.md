---
description: "KDR-X: print the assembled research report"
argument-hint: "--run-dir <dir>"
---

# /kdr:report

Print the assembled report for a persisted run. `kdr report` is read-only: it
emits the Markdown on stdout and persists nothing.

## Steps

1. Read `delivery/report.md` from the run directory.
2. Print it on stdout, verbatim.

The report itself is assembled by the research pipeline (`kdr run` or the
`kdr-deep-research` workflow). Assembling and sealing the DELIVERY — manifest
with `verified_report_hash`, sealed `artifact_hashes`, gate verdicts persisted
with timestamps — is `kdr seal --run-dir <dir>`, never `kdr report` (see
`/kdr:seal`).

## Invariants

- Fact, inference and recommendation are kept distinct.
- Every material claim carries a standing and confidence basis.
- Citations exist *and* support the claim.
- The report discloses gaps, limitations and disagreement.

`kdr report --run-dir <dir>` prints the assembled Markdown; it does not write
or seal anything.
