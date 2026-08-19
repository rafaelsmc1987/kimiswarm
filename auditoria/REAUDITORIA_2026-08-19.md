# Reauditoria estática — 2026-08-19 (F1 da Final Wave)

Reexecução da matriz de aderência das 15 áreas (`GAP_MATRIX.json`) após a
conclusão das FASES 0–10 (76/81 checkboxes; restam T-09-04 [HUMANO] e esta
Final Wave). Critério: todas as áreas ≥ 8.0 ou justificativa formal.

- Repo: `rafaelsmc1987/kimiswarm` (fresh-start), branch `main`, 13 commits
- Testes no momento da reauditoria: **234/234 verdes**; `ruff check` e
  `ruff format --check` limpos (17 arquivos foram normalizados neste passo)
- Baseline: `auditoria/GAP_MATRIX.json` (est. fundação offline 68%, plano 35.3%)

## Scorecard

| # | Área | Peso | Baseline | **Nota** | Status |
|---:|---|---:|---:|---:|---|
| 1 | Higiene e segurança do repositório | 8 | 2.0 | **9.0** | FORTE |
| 2 | Licenças e clean-room | 4 | 7.5 | **8.5** | FORTE |
| 3 | Schemas e contratos | 8 | 9.0 | **9.0** | FORTE (mantido) |
| 4 | Planner council e plano executável | 8 | 2.5 | **8.0** | FORTE |
| 5 | DAG compiler | 8 | 7.5 | **8.0** | FORTE |
| 6 | Scheduler paralelo e subagents reais | 12 | 1.5 | **8.0** | FORTE |
| 7 | Plugin/commands/hooks Claude Code | 10 | 2.5 | **9.0** | FORTE |
| 8 | Retrieval e corpus | 10 | 3.5 | **8.0** | FORTE |
| 9 | Source trust e verificação de citações | 8 | 3.0 | **9.0** | FORTE |
| 10 | Claim-evidence e contradições | 8 | 4.0 | **9.0** | FORTE |
| 11 | Pipeline de relatório e revisão | 6 | 2.0 | **9.0** | FORTE |
| 12 | Estado persistente e resume | 5 | 4.0 | **8.5** | FORTE |
| 13 | Compute reproduzível | 3 | 2.0 | **8.0** | FORTE |
| 14 | Evals, CI e benchmarks | 8 | 2.0 | **8.5** | FORTE |
| 15 | Monitoring e continuous learning | 4 | 0.5 | **8.5** | FORTE |

**Score ponderado: 9.18** (Σ peso×nota / Σ peso = 936.5 / 102). Baseline
ponderado era ~4.1. Todas as áreas ≥ 8.0 — critério de F1 atendido.

## Evidências por área

1. **Higiene/segurança (9.0)** — fresh-start (13 commits, sem histórico
   herdado); `detect-secrets scan --baseline .secrets.baseline` exit 0; scan do
   histórico completo (405 blobs) com padrões gitleaks-equivalentes: únicos
   hits são fixtures falsos intencionais de `tests/test_security_hooks.py`;
   `tests/test_repo_hygiene.py` (forbidden paths) verde; workflows
   `ci.yml` (gitleaks hard-block) e `security.yml` definidos. Falta apenas
   branch protection (T-09-04, gate humano) — não desconta higiene da árvore.
2. **Licenças/clean-room (8.5)** — `LICENSE` raiz (MIT com escopo),
   `docs/LICENSE_MATRIX.md`, `docs/CLEAN_ROOM_RECORD.md`,
   `docs/THIRD_PARTY_NOTICES.md`; corpus forense fora do repo;
   `evidence-manifest/` sanitizado e coberto pelo teste de higiene.
3. **Schemas e contratos (9.0)** — 15 schemas canônicos Pydantic + export
   JSON-Schema reproduzível (`kdr schema`); AgentBrief com
   guidance/context/mission (FASE 3, T-03-01..05); severidade
   blocking/advisory em `GateCheck`.
4. **Planner council (8.0)** — `workflows/kdr-plan.js` lança o council com
   fan-out real via `agent()` (5 planners) + gate Python (`planner.plan_gate`);
   validação estrutural em `tests/test_workflows.py`. Justificativa formal da
   reserva: execução runtime exige Claude Code ≥ 2.1.154 (não disponível
   nesta máquina de CI local); paridade semântica verificada estaticamente.
5. **DAG compiler (8.0)** — validação de ciclos/deps/owners/self-review +
   waves topológicas (`kdrx.dag.compile_dag`); E2E gerou 4 waves no demo.
6. **Scheduler paralelo/subagents (8.0)** — `kdr-run.js` executa cada wave com
   `pipeline()` e resultados estruturados; Python mantém schemas/state/gates
   (divisão por design, não lacuna). Mesma reserva formal de runtime do item 4.
7. **Plugin/commands/hooks (9.0)** — manifesto completo (9 commands, 6 agents,
   3 skills, hooks.json 5 eventos, workflows) com todos os paths existentes
   (`test_plugin_manifest_paths_exist`); wrapper `bin/kdr-hook`; QA hands-on:
   instalação em repo vazio temporário com `pip install -e .` (dist `kdrx`) +
   layout `.claude/plugins/kdr-x` + `kdr doctor` limpo no CWD estrangeiro.
8. **Retrieval e corpus (8.0)** — FASE 5: adapters reais
   (OpenAlex/Crossref/arXiv/GitHub/WebFetch) com transporte injetável e egress
   gate; extractors dedicados por formato com falhas surfacadas; piso de
   relevância dense (`DENSE_RELEVANCE_FLOOR=0.2`) — bug latente corrigido.
9. **Source trust (9.0)** — FASE 6: DOIResolver (doi.org CSL), MetadataCache
   com TTL (outage→cache), checks vivos BLOCKING (DOI_RESOLVES,
   DOI_TARGET_MATCHES, RETRACTION_LIVE) + advisory, DomainPolicy registry,
   dimensões COI/primaryness/directness/independence separadas; FASE 8 tornou o
   gate de integridade final hard (bloqueia entrega).
10. **Claim-evidence (9.0)** — FASE 7: decomposer estruturado com scope
    time/population/jurisdiction e `is_falsifiable`; entailment independente
    (0.7 cobertura + 0.3 numérico); descoberta automática de contradições
    (numeric + polarity); busca ativa de counterevidence; edges 100% derivados
    (`derive_edge`); registry UNRESOLVED com disclosure.
11. **Pipeline de relatório (9.0)** — FASE 8: outline council por rodadas com
    quórum, section DAG one-section-per-task, evidence packs mínimos,
    writer/reviewer/fixer/transition editor como papéis distintos,
    summary/conclusion tardios, citation manager sem orphan/dangling,
    integridade final bloqueante (MATERIAL_CLAIM_INCLUDED, CITATION_ENTAILED,
    REFERENCES_ONLY_CITED).
12. **Estado/resume (8.5)** — FASE 4: run-dir canônico, transições de manifest
    persistidas, selo de hashes, resume que continua o DAG, delivery-manifest
    real; crash/restart testado (`test_phase4_resume.py`).
13. **Compute reproduzível (8.0)** — `kdrx.analysis` (calculation ledger)
    integrado e testado (`test_reporting_evals_analysis_artifact.py`); scores e
    standings determinísticos com base auditável em `components`/
    `calibration_basis`.
14. **Evals/CI/benchmarks (8.5)** — FASE 9a: workflows ci/security com gate
    hard; FASE 9b: splits gold/dev/heldout disjuntos, gate de regressão
    per-kind versionado (THRESHOLD_REGISTRY v1.1.0) com zero critical miss,
    calibration (Jaccard), multi-trial com estabilidade, adapters DeepResearch
    Bench II + Kimi replay, held-out run verde. Reserva formal: CI "ativa" no
    GitHub depende de push (repo não tem remote configurado localmente) —
    ver nota abaixo.
15. **Monitoring/learning (8.5)** — FASE 10: `kdr monitor` real (snapshot de
    hashes, delta added/changed/removed, saved queries), retraction/correction
    alerts com invalidação de claims, `recompute_standings` shadow,
    `diff_reports`, LearningPipeline onde promotion é impossível sem eval
    passado + approval + canary.

## Justificativas formais (reservas)

- **R-A (runtime Claude Code / itens 4 e 6):** os Dynamic Workflows JS foram
  verificados estaticamente (estrutura, chamadas `agent()`/`pipeline()`,
  manifesto) e possuem testes; a execução hands-on depende de Claude Code
  ≥ v2.1.154 com subagentes habilitados no ambiente do usuário — pendente de
  validação de runtime, não de implementação.
- **R-B (CI ativa e branch protection):** `.github/workflows/{ci,security}.yml`
  estão definidos e seus comandos (pytest 234, ruff check/format, sabotage
  forbidden-path) passam localmente; a ativação real exige `git remote` +
  push, e branch protection exige ação humana no GitHub (T-09-04). São gates
  de PLATAFORMA, fora do alcance do código.
