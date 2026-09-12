---
description: "KDR-X: resume from verified kernel checkpoints"
argument-hint: "--run-dir <dir> --corpus <dir> [--backend-config <file>]"
---

# /kdr:resume

Invoke `kdr resume` with the existing run directory and corpus. Supply the same local backend configuration for a live run. Do not synthesize successful results, repair hashes by hand, or restart completed tasks.

The kernel verifies persisted artifacts and reconstructs the index from immutable source snapshots. A missing receipt, incompatible configuration or integrity error must be reported. Preserve the run and database for recovery. Confirm delivery separately with `kdr verify-delivery`.
