# Clean-room record

This document records the boundary between requirements observation and
implementation, so the commercial path is provably clean (plan §46, P0).

## Boundary

- **ARS** (`Imbad0202/academic-research-skills`) is **CC BY-NC 4.0**. No prompt,
  file, code string, or template from ARS was copied into this repository.
- The epistemic requirements (source verification, claim integrity, integrity
  gates, devil's advocate, evidence hierarchy, PRISMA/RoB/GRADE adapters,
  material passport, anti-silent-upgrade, eval harness, seeded defects, model
  tiering) were **re-expressed in our own language** in
  `Plano/PLANO_SOTA_SUPER_DEEP_RESEARCH.md` §6.5 and implemented independently
  in `kdrx/`.

## What "clean-room" means here

1. Requirements were written first, in our own words.
2. Implementation derives from those requirements, not from ARS text.
3. No verbatim prompt/code transfer occurred.
4. This record plus `LICENSE_MATRIX.md` is the audit trail.

## Implementation notes

- `kdrx.verification` — source identity/retraction/COI/currency and the
  prompt-injection boundary, written from the §20/§32 requirements.
- `kdrx.claims` — atomic decomposition, standing, calibration, from §22–24.
- `kdrx.reporting` — citation/claim integrity gate and unsupported-sentence
  detector, from §29 wave 6 and DoD §44.
- `kdrx.evals` — seeded-defect harness, from §36–38.

If a future change imports ARS material, it must not land in the commercial
tree; open a tracking issue instead.
