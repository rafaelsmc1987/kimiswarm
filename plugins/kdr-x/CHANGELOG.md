# Changelog

Mudanças notáveis do plugin `kdr-x` (e do pacote `kdrx`, versionado em
conjunto — ver `scripts/build_plugin_package.py`). Formato baseado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [0.3.0] - Unreleased local candidate

- Transactional run state, task leases, immutable evidence snapshots and stricter delivery validation.
- Dependency-ready concurrent scheduler and versioned kernel requests for host facades.
- Selectable Codex and Claude Code inference adapters with five model specialists over a local corpus; live validation pending.
- Explicit capability/plan status and preserved intermediate regression evidence. No comparative SOTA claim.
- Per-attempt staging and SQLite schema 2 projections commit task artifacts, receipts and checkpoints together; interrupted exports recover without repeating committed work.
- Typed evidence checkpoints, read-only completed resume, lease heartbeats, expiry reconciliation and cooperative cancellation.
- Recoverable delivery publication, separate seal gates and explicit `deliverable` results; `recover-exports` and retention-based, reversible `gc` quarantine.
- Executor registry checked during planning; arbitrary task IDs, deterministic claim assessment and JSON evidence export. Code execution remains unavailable without a validated sandbox.

## [0.2.0] - 2026-08-20

### Added

- Hooks nativos do Claude Code (SW-00): dispatcher dual-mode — payloads
  nativos (`hook_event_name`/`session_id`) roteiam para `kdrx.native_hooks`
  com session registry (binding sessão ↔ run); payloads sintéticos seguem o
  contrato legado.
- `kdr doctor` com health checks do plugin: origem do import
  (`kdrx.__file__`, versões `kdrx`/`pydantic`), completude do manifesto,
  paridade role-resolution ↔ `AgentRole`, writability de `.research` e
  scheduler smoke (WARN degrada sem falhar; FAIL retorna exit 1).
- Manifesto declara os 16 agents explicitamente, com prefixo `./` em todos
  os paths (`commands`, `agents`, `skills`).
- Hooks em exec form (`kdr hook --stdin <event>`) — cross-platform, sem
  shell; `kdr hook` ganha o grupo mutuamente exclusivo `--json`/`--stdin`.
- `scripts/build_plugin_package.py`: pacote de release determinístico
  (`dist/kdr-x-plugin-<versão>.zip` + `dist/SHA256SUMS`, wheel opcional).

### Changed

- Dispatcher de hooks movido do plugin para o pacote
  (`src/kdrx/hook_dispatch.py`), sem mudança lógica; `hooks/kdr-hook` vira
  shim de dev/debug que delega para `kdrx.hook_dispatch.main`.
- `commands/doctor.md` reescrito para descrever exatamente os checks reais
  do `kdr doctor` (evals permanecem no comando separado `kdr eval`).

### Removed

- Wrapper POSIX-only `bin/kdr-hook` (sh) — substituído pelo exec form.

### Fixed

- 10 dos 16 agents estavam invisíveis no harness: o array `agents` do
  manifesto substitui o scan default e omitia os não declarados.
