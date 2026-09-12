---
description: "KDR-X: execute the persisted kernel plan"
argument-hint: "--run-dir <dir> --corpus <dir> [--backend-config <file>]"
---

# /kdr:run

Invoke `kdr run --run-dir <dir> --corpus <dir>` with literal arguments. For a live plan, supply the local `--backend-config` file for its selected Codex or Claude Code backend. Authentication stays in the CLI credential store; never request or print credentials.

The kernel loads the exact persisted plan, dispatches dependency-ready tasks and validates outputs. Do not launch a second scheduler, write task result files yourself, switch providers silently or treat agent prose as proof of completion.

A zero call budget blocks model execution. Propagate kernel errors and failed_tasks. After execution, use `kdr verify-delivery --run-dir <dir>` to determine delivery eligibility; completed tasks alone are insufficient. Live integration remains unverified until a real run produces receipts.
