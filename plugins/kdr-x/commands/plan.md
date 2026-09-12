---
description: "KDR-X: create the canonical kernel plan"
argument-hint: "<objective> [--backend offline|codex|claude-code]"
---

# /kdr:plan

Use the installed `kdr plan` CLI to create the contract and canonical plan. Pass the objective literally through `--objective-file` in an exclusively created temporary file, or a versioned `kdr request` payload. Never use a shared objective filename.

Select `--backend codex` or `--backend claude-code` when the user has requested that provider; otherwise use the offline backend. A live plan adds five explicit specialist tasks over the supplied file corpus. Creating a plan makes no model call.

Only the kernel writes plan.json, manifests, ownership and task projections. Do not create alternate task/wave lists or report a model council as executed when it was not. Return the kernel run_id and plan hash. Do not launch agents from this command.
