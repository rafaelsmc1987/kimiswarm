---
description: "KDR-X: check actual local capability and report unverified integrations"
argument-hint: "--profile offline|plugin|live [--backend codex|claude-code]"
---

# /kdr:doctor

Invoke `kdr doctor --profile <profile> --json`. For live checks select `--backend codex` or `--backend claude-code`.

Report the returned checks and limitations. An installed or authenticated CLI is not a live execution receipt. This command does not make model calls or read credential contents. Do not change providers, install mutable latest dependencies, or turn failed checks into warnings.
