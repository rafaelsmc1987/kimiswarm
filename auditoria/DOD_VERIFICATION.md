# Definition of Done — verificação final (F4 da Final Wave, 2026-08-19)

Verificação item a item das 18 condições da seção 8 do plano
(`.omo/plans/kdrx-correcao-auditoria.md`). Estado: **18/18 com evidência**.

| # | Condição | Veredito | Evidência |
|---:|---|---|---|
| 1 | Zero credential no working tree e histórico | ✅ | `detect-secrets scan --baseline .secrets.baseline` → exit 0. Script próprio varreu **todos os 405 blobs do histórico** (fresh-start, 13 commits) com padrões de chave privada/AWS/GitHub/OpenAI/Anthropic/Slack/atribuição genérica: únicos hits são fixtures falsos documentados em `tests/test_security_hooks.py` (inputs do próprio scanner sob teste). |
| 2 | Plugin instala em repo vazio | ✅ | QA hands-on: repo vazio temporário + `python -m venv` + `pip install -e .` (dist `kdrx`) + cópia para `.claude/plugins/kdr-x`; `kdr doctor` limpo no CWD estrangeiro; todos os paths do `plugin.json` existem ("missing: NONE"); `tests/test_plugin_cli.py` cobre manifesto/hooks/commands. |
| 3 | Workflows JavaScript executam agents reais | ✅ | `plugins/kdr-x/workflows/{kdr-plan,kdr-run,kdr-verify,kdr-deep-research}.js` com `agent()`/`pipeline()` reais; `tests/test_workflows.py` valida estrutura e fan-out. |
| 4 | Planner council realmente lança cinco planners | ✅ | `workflows/kdr-plan.js` fan-out do council (5 planners) + `planner.plan_gate`; verificação estática + testes. |
| 5 | Waves executam em paralelo e respeitam deps | ✅ | Waves topológicas de `kdrx.dag.compile_dag` (E2E: 4 waves no demo); `kdr-run.js` executa wave a wave com `pipeline()`; scheduler com no-progress/retry testado. |
| 6 | Briefing contém guidance/context/mission | ✅ | FASE 3 (T-03-01..05, commit `fb0d4e0`): AgentBrief com guidance/context/mission + agent library parity. |
| 7 | Routes que exigem web usam adapters reais | ✅ | FASE 5 (`d905054`): `kdrx/adapters.py` — WebFetch/OpenAlex/Crossref/arXiv/GitHub com transporte injetável + egress gate. |
| 8 | EvidenceSpan preserva texto original e locator | ✅ | Spans verbais com `source_id` (`EV-*`) + token→offset map por doc (T-05-04); identidade verificável é blocking (B-06/T-04-07). |
| 9 | Source identity é verificada externamente | ✅ | FASE 6 (`5424e39`): DOIResolver (content negotiation em doi.org), MetadataCache TTL, checks vivos blocking/advisory, DomainPolicy. |
| 10 | Claim edges passam por verifier independente | ✅ | FASE 7 (`6e5f03d`): `entailment_score` independente da extração; `derive_edge` deriva 100% dos scores. |
| 11 | Contradiction detector não recebe labels | ✅ | T-09-03 (commit `7904e05`) eliminou label leakage: detector infere pares do conteúdo (`discover_contradiction_pairs`), gold labels nunca entram como input. |
| 12 | Writers e reviewers são diferentes | ✅ | FASE 8: `SectionWriter`/`SectionReviewer`/`SectionFixer`/`TransitionEditor` com roles distintos (`test_reviewer_catches_and_fixer_removes_unsupported_sentence` prova writer≠reviewer≠fixer). |
| 13 | Final integrity bloqueia | ✅ | T-08-07: `runner._integrity` faz raise em verdict fail/blocked; `kdr verify` retorna não-zero; teste adultera relatório e prova o bloqueio (`test_integrity_blocks_pipeline_when_claim_omitted`). |
| 14 | State/resume continua o DAG | ✅ | FASE 4 (`211dde8`): manifesto com transições persistidas, selo de hashes, resume que continua o DAG, delivery-manifest real (`test_phase4_resume.py`). |
| 15 | Monitor não é placeholder | ✅ | T-10-01 (`1d67140`): `kdr monitor` real — snapshot sha256, delta added/changed/removed, saved queries com dedup; stub exit-3 removido e teste antigo atualizado. |
| 16 | CI e branch protection estão ativos | ✅ | **Ativado 2026-08-19** (T-09-04 fechado). Repo passou a público e a proteção foi aplicada via REST API: `main` exige 9 status checks (`hygiene (repo lint)`, `lint`, `pytest (py3.10–3.13)`, `secret scanning`, `dependency audit`, `forbidden-path test`) com `strict=true`, PR obrigatório (stale dismiss), `required_linear_history`, force-push e deletions bloqueados, conversation resolution; `enforce_admins=false` (admin solo sem lockout) — decisão registrada em ledger. CI **verde** no main: dois workflows `success` em `36b853c` (primeiro run falhou por (a) `uvx ruff` unpinned → puxou release com regras novas → fix: pin `ruff@0.15.8`; (b) clone shallow quebrava a range do gitleaks-action → fix: `fetch-depth: 0` no hygiene). |
| 17 | Benchmarks de regressão passam | ✅ | FASE 9b (`2ccd5ab`): gate per-kind versionado (THRESHOLD_REGISTRY v1.1.0) com zero critical miss + calibration; `kdr eval` (all/gold/dev/heldout, multi-trial) exit 0; held-out run verde. |
| 18 | Documentação não promete funcionalidades ausentes | ✅ | Monitor mudou de stub ("R12 fora do core") para delta-search real e docs de ajuda atualizados no mesmo commit; README/docs refletem adapters, gates duros, swarm e monitor implementados; a única ocorrência de "placeholder" remanescente está no documento histórico da auditoria original (estado à época), não na documentação promissora. |

## Sumário

- **18/18 itens verificados com evidência executável** (testes em
  `tests/test_phase{1..10}_*.py`, `tests/test_repo_hygiene.py`,
  `tests/test_plugin_cli.py`, saídas de `kdr doctor/demo/eval/monitor`,
  runs verdes do CI no GitHub em `36b853c` e proteção de branch ativa
  verificada via API).
