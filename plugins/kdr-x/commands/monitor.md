---
description: "KDR-X: delta-search, retraction alerts and standing diffs"
argument-hint: "[--run-dir <dir>]"
---

# /kdr:monitor

Continuous monitoring (route R12): a saved query plan re-runs on a schedule,
classifies new sources, raises retraction alerts and diffs the report.

## Steps

1. Load the saved query plan and re-issue the query graph.
2. Retrieve only *new* documents (delta retrieval by content hash).
3. Classify new sources and re-run source-trust checks.
4. Emit standing changes as `standing` diffs, not silent rewrites.
5. Re-run the integrity gate on the diffed report.

## Invariants

- Monitoring never mutates a sealed artifact; it appends deltas.
- Retraction/correction of a cited source is surfaced immediately.

The deterministic offline core records deltas; live adapters plug in via the
`SourceRecord` interface. See `kdrx/retrieval.py`.

