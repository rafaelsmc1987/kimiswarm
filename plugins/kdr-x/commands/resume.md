---
description: "KDR-X: verify hashes and resume an incomplete run"
argument-hint: "--run-dir <dir>"
---

# /kdr:resume

Resume an interrupted run without redoing completed work.

## Steps

1. Load `manifest.json` via `kdrx.state.RunState.load_manifest`.
2. Verify artifact hashes (`RunState.verify_hashes`); any change is reported,
   never silently overwritten.
3. Rebuild the ready queue: completed tasks stay done, only incomplete nodes
   re-enter the wave scheduler.
4. Resume with `kdrx.scheduler.WaveScheduler` from the first pending wave.

## Invariants

- Resume is idempotent: running twice is a no-op if nothing changed.
- Hash mismatch blocks resume until acknowledged.

Use `kdr resume --run-dir <dir>` for the deterministic check.

