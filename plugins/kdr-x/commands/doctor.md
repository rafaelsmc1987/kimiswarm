---
description: "KDR-X: self-check schemas, scheduler and gates"
argument-hint: ""
---

# /kdr:doctor

Verify the deterministic core and the plugin installation are healthy before
trusting a run.

## Checks

- **import origin** — prints `kdr`/`kdrx` versions, `kdrx.__file__` (skew
  between the pip-installed kernel and this plugin is observable here) and
  the `pydantic` version; lists the 15 canonical schemas.
- **plugin manifest** — agents/commands/skills declared in
  `.claude-plugin/plugin.json` match the files on disk (both directions).
- **role-resolution parity** — `agents/role-resolution.json` keys are exactly
  the `AgentRole` enum values, every target resolves to an existing
  `agents/<nome>.md`, and every `agents/*.md` is declared in the manifest.
- **`.research` writable** — write probe (mkdir + temp file + remove) under
  the current directory; every run needs it.
- **scheduler smoke** — the wave scheduler completes a trivial 1-task DAG.

## WARN vs FAIL and exit codes

The plugin root is discovered via `KDRX_PLUGIN_ROOT`, then
`CLAUDE_PLUGIN_ROOT`, then an upward search from the cwd. Outside a
checkout/plugin install, the manifest and parity checks degrade to
`plugin manifest: WARN` (skipped) — WARN never fails the command. Any FAIL
(manifest mismatch, parity mismatch, `.research` not writable, scheduler
smoke failure) makes `kdr doctor` exit `1`; otherwise it exits `0`.

The seeded-defect eval suite is a separate command: `kdr eval`.
