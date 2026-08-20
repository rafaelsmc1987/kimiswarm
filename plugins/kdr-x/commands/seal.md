---
description: "KDR-X: verify-then-seal the final report bytes and persist the delivery"
argument-hint: "--run-dir <dir> [--json]"
---

# /kdr:seal

Deterministic verify-then-seal over the FINAL bytes of `delivery/report.md`.
Re-runs the canonical gates (`source_trust`, `citation_integrity`, `security`,
`plan_dag`) over the exact bytes on disk, persists the verdicts with
timestamps, and — only if every gate passes — seals `artifact_hashes` and
emits `delivery-manifest.json` with `verified_report_hash`
(validate-then-write: a failing seal writes NO seal).

## Steps

1. Load `manifest.json` and `plan.json`; compile the DAG.
2. Load `corpus/sources.jsonl`, `evidence/spans.jsonl`, `claims/claims.jsonl`.
3. Read `delivery/report.md` in BYTES (CRLF-safe; the hash is of the bytes on
   disk, never of a re-encoded copy).
4. Run the gates over those bytes.
5. Persist `verification/integrity.json` + `verification/security.json` ALWAYS
   (audit trail with `verdict` + `timestamp`), even when a gate fails.
6. If all gates pass: set `artifact_hashes`, `metadata.seal`,
   `delivered_at`, `gate_timestamps`, emit `delivery-manifest.json` with
   `verified_report_hash` and append the `delivery_sealed` event.
7. Print JSON on stdout: on pass `{verdict, sealed, run_dir,
   verified_report_hash, delivered_at, gate_timestamps}`; on gate failure
   `{verdict: "fail", sealed: false, gate_results, blocking_reasons}`.

## Exit codes

- `0` — sealed: every gate passed, seal written.
- `1` — gate failed: verdicts persisted, NO seal written (validate-then-write).
- `2` — usage/IO: run dir, manifest, plan, sources/spans/claims or report
  missing/unreadable.
- `3` — `plan.json` corrupt (pydantic validation error).

## Invariants

- `verified_report_hash` is the sha256 of the report bytes on disk at seal
  time.
- Re-seal is idempotent: same bytes → same hash; `metadata.seal.revision`
  increments; changed bytes are re-verified and re-hashed (revision-safe).
- A sealed artifact is immutable inside a bound session
  (`SEALED_ARTIFACT_WRITE` blocks Write/Edit; tamper is caught by the Stop
  hash checks).

## Unresolved critical claims

- `kdr seal` attests the hashes/gates and records `unresolved_critical_claims`
  in `delivery-manifest.json`, but it does NOT block on CRITICAL+UNRESOLVED
  claims.
- Resolving critical claims remains the Stop hook's gate (`CRITICAL_RESOLVED`
  blocks delivery while critical claims stay unresolved).
- `cmd_seal` emits a warning line on stderr when unresolved critical claims
  exist.

`kdr seal --run-dir <dir>` (add `--json` for machine-readable output) is the
only command that persists verdicts and the delivery seal; `kdr verify` is the
read-only adversarial re-run.
