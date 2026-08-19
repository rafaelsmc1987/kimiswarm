---
description: "KDR-X: assemble and deliver the research report"
argument-hint: "--run-dir <dir>"
---

# /kdr:report

Assemble the report from the evidence pack and deliver the artifact.

## Steps

1. Load the evidence pack (`kdrx.reporting.build_evidence_pack`).
2. Assemble dependency-ordered sections via `kdrx.reporting.ReportAssembler`
   (outline -> body -> dependent synthesis -> review -> citation/integrity ->
   mechanical assembly, plan §29).
3. Run the citation/integrity gate before delivery.
4. Write `delivery/report.md` and a `DeliveryManifest` with sealed artifacts
   (`kdrx.artifact`).

## Invariants

- Fact, inference and recommendation are kept distinct.
- Every material claim carries a standing and confidence basis.
- Citations exist *and* support the claim.
- The report discloses gaps, limitations and disagreement.

`python3 -m kdrx.cli report --run-dir <dir>` prints the assembled Markdown.
