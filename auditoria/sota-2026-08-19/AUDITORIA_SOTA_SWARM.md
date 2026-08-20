
# Auditoria SOTA de Swarm — `rafaelsmc1987/kimiswarm`

**Data:** 19 de agosto de 2026  
**Branch:** `main`  
**Commit auditado:** `08f927dd8feeb1c856deb2cda991ee14f46dfce9`  
**Método:** inspeção estática profunda via GitHub Connector; comparação com o checklist anterior, a documentação atual do Claude Code e pesquisa recente sobre coordenação multiagente.  
**Limitação:** o código e os workflows Claude não foram executados nesta sessão. A análise distingue cuidadosamente presença de código, teste estrutural e prova operacional.

---

# 1. Veredito executivo

O repositório evoluiu muito. Ele deixou de ser um corpus forense com um MVP e passou a conter:

- kernel determinístico de pesquisa;
- schemas e DAG;
- state/resume;
- source trust;
- claim-evidence graph;
- report pipeline;
- monitor e learning primitives;
- plugin Claude Code;
- quatro Dynamic Workflows;
- biblioteca de agentes;
- CI e security workflows.

Porém:

> **O repositório ainda não é um swarm SOTA de produção.**

Ele contém dois sistemas parcialmente separados:

```text
A. Kernel Python
   schemas + DAG + state + retrieval + claims + gates + report
   porém executor offline/sequencial

B. Workflows JavaScript
   agents paralelos reais
   porém plano compacto, workers genéricos, state/gates parcialmente mediados
   e integração incompleta com o kernel
```

A meta agora é criar uma única execução canônica em que:

```text
planner real
→ ResearchPlan completo persistido
→ specialist agents reais
→ durable scheduler
→ adapters e claim graph
→ report swarm
→ final verification
→ immutable sealed artifact
```

## Pontuação de prontidão SOTA

**48.1/100**

Essa nota é um julgamento de engenharia, não um resultado de benchmark. O checklist anterior pode estar quase todo coberto no nível de arquivos e primitives, mas “SOTA swarm” exige coordenação adaptativa, durabilidade, contenção, observabilidade e superioridade empírica.

---

# 2. Scorecard

| Dimensão | Peso | Nota | Estado | Diagnóstico |
|---|---:|---:|---|---|
| Kernel determinístico: schemas, DAG, gates e artifacts | 10 | 8.5/10 | **FORTE** | Boa base Pydantic/DAG/state/claims, mas ainda não é o runtime que coordena os agentes reais. |
| Planejamento e compilação do DAG | 8 | 7.0/10 | **BOM_COM_GAP_CRITICO** | Planner council existe, porém o plano sintetizado pelo workflow não é persistido e revalidado como o ResearchPlan canônico. |
| Orquestração multiagente real | 15 | 5.0/10 | **PARCIAL** | Há parallel()/pipeline(), mas workers genéricos não usam a biblioteca de agentes, TaskSpec completo, retries duráveis ou ownership transacional. |
| Seleção adaptativa de arquitetura e replanning | 10 | 2.5/10 | **AUSENTE** | Não escolhe single/centralized/hybrid/team conforme decomposability, sequentiality, tool density, incerteza e custo; DAG é essencialmente fixo. |
| Especialização, comunicação e integração distribuída | 8 | 3.5/10 | **FRACO** | Existem 17 definições e role-resolution, mas workflows usam agent() genérico; não há blackboard, directed peer requests ou protocolo de integração. |
| Durabilidade, recuperação e execução distribuída | 10 | 4.0/10 | **PARCIAL** | Python tem manifest/resume, mas workflows só retomam plenamente na mesma sessão Claude e não há leases, heartbeats, idempotency ou fila durável. |
| Rigor epistemológico do deep research | 10 | 6.5/10 | **BOM_MAS_HEURISTICO** | Claim graph, source trust e falsification existem, porém entailment/contradição/ranking ainda dependem muito de regras lexicais e proxies. |
| Context engineering e memória | 7 | 3.0/10 | **FRACO** | Sem context-pack builder, relevância por artifact, compaction por fase, cache-aware batching ou memória governada conectada à execução. |
| Segurança e contenção por worker | 8 | 4.5/10 | **PARCIAL** | Há hooks/egress/secret guards, mas workflows rodam acceptEdits, escrevem em diretório compartilhado e o boundary não cobre toda saída Web/MCP. |
| Observabilidade, custo e attribution | 5 | 2.5/10 | **AUSENTE** | Sem OpenTelemetry, spans por agent/tool/query/claim, custo por contribuição, critical path, error amplification ou replay operacional. |
| Evals e prova de superioridade | 6 | 4.0/10 | **PARCIAL** | Há 234 testes declarados e toy/heldout fixtures, mas não há live Claude workflow CI, baseline single-agent, ablations, scaling curves ou benchmark results. |
| Packaging, CI e governança | 3 | 4.5/10 | **PARCIAL** | CI existe, mas mypy é advisory; plugin não é totalmente autocontido/cross-platform e a API clássica do branch contradiz a documentação de protection. |


---

# 3. O que está realmente forte

## 3.1 Kernel determinístico

O pacote possui uma base boa para um control plane:

- contratos Pydantic;
- compile_dag;
- ownership;
- retry policy;
- manifest;
- events;
- exact spans;
- source families;
- claim edges;
- integrity/security gates;
- artifact seals.

Essa camada deve ser preservada e transformada na fonte de verdade do swarm.

## 3.2 Dynamic Workflows

Existem scripts com:

- `parallel()` no planner council;
- `pipeline()` por wave;
- schema em resultados;
- tratamento de `null`;
- fases observáveis;
- verificação adversarial.

Isso é um salto real em relação à versão anterior.

## 3.3 Biblioteca de agentes

Há agentes para:

- plan;
- explore;
- general;
- search;
- evidence;
- claims;
- writing;
- review;
- verifier;
- coder em worktree;
- source verification;
- counterevidence;
- final integrity.

O problema não é mais ausência de definições. É fazê-las participar da execução canônica.

## 3.4 Pesquisa e integridade

O repo já inclui:

- DOI/metadata resolution;
- source policy;
- retraction/currency/COI;
- dedup e independence families;
- claim decomposition;
- evidence edges;
- contradiction/falsification primitives;
- report review/fix;
- delta and learning primitives.

Esses componentes formam um kernel de deep research acima da média dos projetos open source, mas ainda precisam de integração semântica e operacional.

---

# 4. Blockers críticos

## S0-01 — Hooks usam payload KDR-X customizado, não o payload nativo do Claude Code

**Severidade:** BLOCKER

**Evidência observada**

- plugins/kdr-x/hooks/kdr-hook espera data['task'] com TaskSpec completo
- SubagentStop/TaskCompleted esperam data['result'] e data['task']
- Claude Code envia task_id/task_subject/task_description ou agent_id/agent_type/transcript paths/last_assistant_message
- tests/test_plugin_cli.py injeta payloads sintéticos criados pelo próprio KDR-X

**Impacto**

Os hooks mais importantes podem falhar com KeyError ou não validar a task/agent real; a conclusão 18/18 não prova enforcement no harness nativo.

**Correção exigida**

1. Criar NativeHookEnvelope por evento e adapters específicos.
2. Persistir session_id -> run_id e task_id nativo -> TaskSpec canônico.
3. Extrair AgentResult do transcript/result artifact no SubagentStop.
4. Emitir JSON/event-specific decision e stderr compatíveis com Claude Code.
5. Cobrir stop_hook_active, recursive stop e ausência de active run.
6. Executar contract tests contra fixtures copiadas da documentação oficial.

## S0-02 — Split-brain entre plano do planner council e plan.json executado

**Severidade:** BLOCKER

**Evidência observada**

- kdr-plan.js cria scaffold Python e depois sintetiza um plano enriquecido
- o plano enriquecido é apenas retornado pelo workflow
- kdr-run.js relê runDir/plan.json, que continua sendo o scaffold padrão
- o PLAN_SCHEMA JavaScript omite grande parte de TaskSpec/ResearchPlan

**Impacto**

As cinco perspectivas podem não controlar o DAG executado; o sistema apresenta planner council sem executar suas decisões.

**Correção exigida**

1. Usar JSON Schema canônico exportado pelo Python no workflow.
2. Adicionar kdr import-plan --run-dir ... --stdin e validar compile_dag + plan_gate.
3. Persistir plan revision, plan hash, provenance dos planners e approval.
4. Bloquear se review.approved=false; implementar revisão/correção até PASS.
5. Nunca aceitar um plano compacto sem role/tools/skills/guidance/context/owner/reviewer/acceptance/retry/budget.

## S0-03 — Relatório final é escrito depois da verificação

**Severidade:** BLOCKER

**Evidência observada**

- kdr-deep-research.js executa a fase verify
- em seguida um novo agent escreve delivery/report.md
- não há nova verificação, citation gate ou seal após essa escrita

**Impacto**

O artefato entregue não é necessariamente o artefato que passou nos gates; uma escrita pós-gate invalida toda garantia de integridade.

**Correção exigida**

1. Ordenar: draft -> review/fix -> assemble -> verify -> seal -> immutable delivery.
2. Proibir qualquer Write/Edit no artifact sealed.
3. Gravar verified_report_hash no DeliveryManifest.
4. Stop hook deve comparar hash atual com o hash verificado.
5. Executar final verifier sobre o relatório exatamente entregue.

## S0-04 — A biblioteca de agentes não é usada pela orquestração

**Severidade:** BLOCKER

**Evidência observada**

- role-resolution.json mapeia dezenas de AgentRole para 17 agentes
- workflows chamam agent(prompt, {label, phase, schema}) sem agent type
- plugin manifest declara somente seis agents e paths não seguem consistentemente './'
- workers herdam modelo/tool allowlist da sessão

**Impacto**

Não há garantia de especialização, least privilege, model routing, worktree, effort ou skills; muitos agentes definidos podem nunca carregar.

**Correção exigida**

1. Corrigir manifest para auto-discovery de agents/ ou paths './agents/'.
2. Gerar AgentExecutionSpec por TaskSpec com agent_type, model, effort, cwd, tools, worktree e schema.
3. Invocar explicitamente os agentes resolvidos em vez de persona textual.
4. Mover controles não suportados por plugin para .claude/agents ou policy global.
5. Adicionar doctor que compara AgentRole enum, role-resolution e agents realmente carregados por `claude agents`.

## S0-05 — Não existe um único E2E que una agentes reais e o kernel canônico

**Severidade:** BLOCKER

**Evidência observada**

- Python: schemas/gates/state/retrieval/claim/report robustos, mas scheduler sequencial e executor offline
- JavaScript: agentes paralelos reais, mas schemas compactos, gates mediados por agents e artifacts parcialmente desconectados
- adapters de produção aparecem no módulo e testes, não no runner/workflow principal

**Impacto**

Cada metade demonstra algo diferente; nenhuma prova o produto SOTA completo.

**Correção exigida**

1. Definir o Python como control API/sidecar determinístico e o workflow como executor.
2. Toda task deve fazer claim/lease via API, receber AgentBrief canônico e commit de AgentResult.
3. Integrar adapters, source trust, claim graph, report swarm e gates no mesmo run.
4. Criar uma golden E2E com web real, múltiplos agentes, conflito, retry, resume e relatório sealed.

## S0-06 — Stop hook não é session-bound e pode escolher o run errado

**Severidade:** HIGH

**Evidência observada**

- procura o diretório mais recentemente modificado sob .research
- CLI usa por padrão .research/runs
- ignora session_id do payload
- unresolved_critical é passado como lista vazia
- reconstrói DeliveryManifest em vez de validar o persistido

**Impacto**

Uma sessão pode ser bloqueada/liberada com base em outro run, em gates obsoletos ou sem claims críticos reais.

**Correção exigida**

1. Criar session registry persistente session_id -> run_id.
2. Nunca usar most-recent-directory como fonte de verdade.
3. Carregar DeliveryManifest persistido, verificar seals e unresolved registry.
4. Exigir gate timestamps/hash posteriores ao relatório final.

## S0-07 — Branch protection declarada não é confirmada pela API clássica

**Severidade:** HIGH

**Evidência observada**

- README e DOD dizem 9 required checks e strict protection
- GET branch atual retorna protected=false, protection.enabled=false e enforcement off
- o commit mais recente está unsigned

**Impacto**

A governança pode estar documentada de forma incorreta, ter sido removida ou existir apenas em ruleset não auditado.

**Correção exigida**

1. Consultar e exportar repository rulesets como artifact de CI.
2. Adicionar governance-verification workflow que falha quando proteção/ruleset diverge.
3. Atualizar README para distinguir classic branch protection de rulesets.
4. Adotar signed tags/releases e, se viável, signed commits.


---

# 5. Gaps importantes restantes

## S1-01 — DAG fixo e sem selector de arquitetura

O scaffold padrão tem quatro tasks e o swarm é usado mesmo sem medir decomposability/sequentiality/tool density. Isso pode degradar tarefas sequenciais.

## S1-02 — Sem replanning dinâmico e stopping loop operacional

QueryGraph e saturation existem no Python, mas o lead não adiciona/remove tasks em resposta a gaps, conflitos, marginal gain, API failures ou novas entidades.

## S1-03 — Falha numa task bloqueia waves inteiras

O workflow interrompe tudo em vez de bloquear apenas descendants; branches independentes não continuam e não há quorum/partial completion policy.

## S1-04 — Sem durable distributed scheduler

Não há leases, heartbeats, idempotency keys, transactional artifact commits, worker reconciliation, dead-letter queue, cancellation propagation ou recovery após sair do Claude Code.

## S1-05 — Shared filesystem sem staging transacional

Múltiplos agents em acceptEdits escrevem diretamente no mesmo run dir; outputs podem colidir, ficar parciais ou ser lidos antes de commit.

## S1-06 — Sem protocolo de comunicação/blackboard

Não há evented blackboard de claims/sources/gaps, peer request dirigida, locks de recursos ou síntese distribuída; compartilhar arquivos não resolve o communication-reasoning gap.

## S1-07 — Context packs e compaction ausentes

Workers recebem prompts ad hoc, não artifact bundles mínimos versionados. Não há relevance retrieval, phase summaries, prompt-cache grouping ou token budgets por task.

## S1-08 — Model routing e cost governance ausentes

Workflows não selecionam modelo/effort por etapa, não registram tokens/custo previsto/real, nem usam escalation/de-escalation por uncertainty.

## S1-09 — Retrieval ainda não é SOTA

O canal dense padrão é char-ngram proxy; faltam embeddings/reranker neural, citation/entity graphs, pagination/retry/rate-limit, JS-rendered web, robust PDF multimodal e cross-lingual retrieval.

## S1-10 — Semântico ainda muito heurístico

Entailment, scope e contradiction usam token overlap/regex/números; faltam verifier semântico independente, cross-model checks, calibration, abstention e adversarial hard negatives.

## S1-11 — Monitoramento é somente file-delta

Salva queries, mas não as reexecuta, não busca web delta, não revalida fontes, não cascata standings nem produz report diffs.

## S1-12 — Learning pipeline não está conectado ao produto

A state machine de learning é in-memory em evals.py; não há observation ingestion, versioned candidate, PR bot, canary production, rollback ou provenance.

## S1-13 — Security boundary incompleta

Hooks cobrem algumas ferramentas de escrita; não inspecionam sistematicamente WebSearch/WebFetch/MCP/Agent outputs. Adapters não têm SSRF/redirect/DNS-rebinding/size/content-type/circuit-breaker completos.

## S1-14 — Observabilidade inexistente

Sem OpenTelemetry, traces por run/wave/task/agent/tool/query/source/claim/gate, cost attribution, contribution score, error amplification, critical path e deterministic replay.

## S1-15 — Evals não provam SOTA

Testes de workflows são estruturais; não há execução real Claude em CI, single-agent baseline, architecture ablation, scaling curve, Silo-Bench/DPBench, DeepResearch Bench results ou cost-quality Pareto.

## S1-16 — CI/release ainda incompletos

Mypy é advisory; sem coverage floor, mutation/property/fuzz, Windows/macOS, plugin marketplace install E2E, live contract tests, SBOM/SLSA e release workflow.


---

# 6. Por que “mais agents” não é SOTA

Um swarm SOTA não tenta maximizar o número de agentes. Ele seleciona uma arquitetura baseada na tarefa:

```text
sequential / high coupling
→ single agent ou pipeline estreita

parallelizable / broad evidence
→ centralized fan-out

distributed private state
→ hybrid / directed peer communication

contention over shared resources
→ external scheduler, leases and locks
```

Portanto, o KDR-X precisa medir:

- decomposability;
- sequential dependency ratio;
- number of independent evidence dimensions;
- tool density;
- uncertainty;
- coordination cost;
- expected value of parallelism;
- risk of error propagation.

Sem isso, o sistema pode gastar mais e produzir pior resultado.

---

# 7. Arquitetura alvo

```text
User / Claude Code / API
        ↓
Research Contract
        ↓
Architecture Selector
        ↓
Durable Orchestrator + Event Store
        ↓
Versioned DAG + Queue + Leases
        ↓
Model Router + Tool Router + Context Router
        ↓
Specialist Workers in Isolated Sandboxes
        ↓
Typed Blackboard + Transactional Artifacts
        ↓
Canonical Corpus + Claim-Evidence Graph
        ↓
Deterministic + Semantic Gates
        ↓
Report Swarm
        ↓
Verify exact final bytes
        ↓
Seal + Delivery Manifest
```

O diagrama completo está em `TARGET_ARCHITECTURE.mmd`.

---

# 8. Plano detalhado por PR

## SW-00 — Native hooks and session-bound run registry

**Fase:** P0 — Correctness  
**Dependências:** nenhuma

**Escopo**

- NativeHookEnvelope por evento oficial
- session_id -> run_id registry
- task_id nativo -> TaskSpec registry
- SubagentStop transcript/result adapter
- TaskCompleted acceptance lookup
- Stop com persisted DeliveryManifest, unresolved claims e seal validation
- paths unificados em .research/runs

**Critérios de aceite**

- Fixtures oficiais TaskCreated/TaskCompleted/SubagentStop/Stop passam
- duas sessões simultâneas nunca cruzam runs
- Stop rejeita report modificado após integrity gate
- nenhum KeyError com payload nativo

## SW-01 — Self-contained cross-platform plugin

**Fase:** P0 — Packaging  
**Dependências:** SW-00

**Escopo**

- Corrigir manifest paths e agent auto-discovery
- Empacotar kernel como wheel/zipapp ou sidecar incluído
- Wrapper Node/Python cross-platform
- plugin doctor usando claude plugin validate e claude agents
- sem dependência de ../../src no projeto consumidor
- semver, changelog e release artifact

**Critérios de aceite**

- instalação em repo vazio Linux/macOS/Windows
- todos 17 agents aparecem
- todos comandos/workflows/hooks funcionam sem checkout do monorepo
- offline uninstall/reinstall reproduz o mesmo hash

## SW-02 — Canonical planner handoff and revision loop

**Fase:** P0 — Canonical plan  
**Dependências:** SW-01

**Escopo**

- Workflow usa ResearchPlan/TaskSpec JSON Schema completos
- kdr import-plan --stdin valida e persiste
- review.approved é gate obrigatório
- review -> repair -> verify loop limitado
- plan revision/hash/provenance
- argumentos passados como JSON, sem interpolação shell

**Critérios de aceite**

- o hash do plano retornado é o hash do plan.json executado
- todo planner recommendation tem disposition
- plano inválido nunca chega a kdr-run
- role/tools/skills/guidance/context/owners/reviewers/acceptance/budget preservados

## SW-03 — Final report verify-then-seal ordering

**Fase:** P0 — Integrity  
**Dependências:** SW-02

**Escopo**

- draft -> review -> fix -> assemble -> verify -> seal
- artifact immutable após seal
- DeliveryManifest contém verified hash e gate timestamps
- Stop compara hash e lineage
- citation/source/claim/numeric/security gates sobre bytes finais

**Critérios de aceite**

- qualquer byte alterado após gate bloqueia
- relatório final e relatório verificado são idênticos
- nenhum Write/Edit permitido em artifact sealed

## SW-04 — Role-aware specialist executor

**Fase:** P1 — Agent runtime  
**Dependências:** SW-02

**Escopo**

- AgentExecutionSpec derivado de TaskSpec
- custom agent type por role-resolution
- model/effort/tools/skills/cwd/worktree por task
- least privilege
- context pack + upstream artifacts
- reviewer/verifier independence constraints

**Critérios de aceite**

- trace mostra agent type/model/tools por task
- search worker não escreve
- coder sempre usa worktree
- autor nunca aprova o próprio output

## SW-05 — Unify JavaScript swarm with Python research kernel

**Fase:** P1 — Unified E2E  
**Dependências:** SW-03, SW-04

**Escopo**

- claim/lease/commit API para tasks
- AgentBrief e AgentResult canônicos
- adapters, source trust, claim graph, report swarm e gates em um run
- Python sidecar determinístico
- artifact transactions e provenance

**Critérios de aceite**

- golden live-web E2E usa 5+ specialist agents
- todos outputs estão no manifest e claim graph
- resume após kill continua sem repetir tasks fechadas
- relatório final sealed passa gates

## SW-06 — Event-sourced durable scheduler

**Fase:** P1 — Durability  
**Dependências:** SW-05

**Escopo**

- Postgres/SQLite event store interface
- ready queue, worker leases e heartbeats
- idempotency keys
- retry/backoff/jitter/dead-letter
- descendant-only blocking
- cancellation and timeout propagation
- staging + atomic artifact commit
- cross-session/cross-process resume

**Critérios de aceite**

- chaos test mata orchestrator e workers em todas waves
- zero output duplicate/corrupt
- branches independentes continuam após falha não relacionada
- dead worker é reconciliado automaticamente

## SW-07 — Architecture selector and adaptive workforce

**Fase:** P1 — Adaptive swarm  
**Dependências:** SW-05

**Escopo**

- features: decomposability, sequentiality, tool density, uncertainty, breadth, value
- routes: single, centralized, independent, hybrid, agent-team
- agent-count and model-budget policy
- cost/quality prediction
- fallback and escalation

**Critérios de aceite**

- selector escolhe single-agent para sequential tasks
- centralized/hybrid para breadth e contradictions
- 87%+ selector accuracy no conjunto interno ou threshold justificado
- multi-agent nunca é default cego

## SW-08 — Dynamic DAG mutation and evidence saturation

**Fase:** P1 — Replanning  
**Dependências:** SW-06, SW-07

**Escopo**

- coverage/gap/contradiction monitor
- versioned DAG mutations
- targeted validation waves
- entity-following and citation chaining
- marginal evidence/source gain
- budget-aware stop
- no-progress detection

**Critérios de aceite**

- novo conflito cria verifier wave automaticamente
- duas rounds sem gain encerram run
- DAG history é auditável e reproduzível
- budget ceiling produz explicit unresolved registry

## SW-09 — Blackboard, directed messaging and resource coordination

**Fase:** P1 — Coordination  
**Dependências:** SW-06

**Escopo**

- typed events for sources/claims/gaps/requests
- scoped subscriptions
- direct peer request somente com rationale
- artifact/resource locks
- deadlock prevention
- A2A-compatible Task/Artifact/Event facade
- integration agents for distributed state

**Critérios de aceite**

- DPBench-inspired contention suite sem deadlock
- Silo-inspired distributed-state tasks integram informação corretamente
- message budget e relevance score limitam chatter

## SW-10 — Context engineering and durable memory

**Fase:** P1 — Context  
**Dependências:** SW-05

**Escopo**

- ContextPack schema
- artifact relevance index
- phase summaries and compaction
- prompt-cache-aware batch grouping
- token budget per role/task
- memory scopes: run/project/global
- governed retrieval of prior experience

**Critérios de aceite**

- context contains only required artifacts
- no hidden sibling dependency
- token use drops without quality regression
- memory contamination tests pass

## SW-11 — Semantic retrieval, entailment and calibrated consensus

**Fase:** P1 — Epistemics  
**Dependências:** SW-05

**Escopo**

- real embeddings + cross-encoder reranker
- citation/entity graph
- semantic claim decomposition
- independent NLI/LLM verifier
- cross-model verifier on critical claims
- semantic contradiction and alternative hypotheses
- calibration/abstention/quorum
- domain evidence policies and RoB/GRADE adapters

**Critérios de aceite**

- hard-negative citation suite
- compound/partial/scope mismatch recall thresholds
- calibration ECE/Brier floors
- critical claims require independent evidence families

## SW-12 — Real multiagent editorial pipeline

**Fase:** P1 — Report swarm  
**Dependências:** SW-11

**Escopo**

- outline council
- section DAG
- parallel specialist writers
- reviewer/fixer pairs
- transition/terminology/citation agents
- late executive synthesis
- mechanical assembly
- final reverify and seal

**Critérios de aceite**

- writer/reviewer/fixer independence
- all claims trace to exact evidence
- orphan/dangling/unsupported/numeric mismatches block
- section-level artifacts survive resume

## SW-13 — Per-worker containment and untrusted-content firewall

**Fase:** P2 — Security  
**Dependências:** SW-05

**Escopo**

- sandbox per worker
- read-only retrieval workers
- egress proxy and domain policy
- SSRF/redirect/DNS rebinding protection
- content size/type limits and circuit breakers
- credential broker
- MCP/tool allowlist
- Web/MCP output quarantine and instruction/data labels
- artifact malware/secret scan

**Critérios de aceite**

- prompt-injection red team cannot mutate task/gate/tool policy
- SSRF metadata endpoints blocked
- worker compromise cannot read sibling secrets/artifacts
- all tool outputs have provenance/trust labels

## SW-14 — OpenTelemetry, cost attribution and deterministic replay

**Fase:** P2 — Observability  
**Dependências:** SW-06

**Escopo**

- trace spans run/wave/task/agent/tool/query/source/claim/gate
- token/cost/latency/model/tool metrics
- critical path and straggler metrics
- agent contribution and duplicated-work score
- error amplification
- privacy redaction
- trace viewer and replay

**Critérios de aceite**

- todo report claim abre trace até source/tool call
- cost por agent/task/claim disponível
- replay reconstrói state sem chamar modelo
- PII/secrets redacted

## SW-15 — Live delta research and governed learning

**Fase:** P2 — Monitoring  
**Dependências:** SW-08, SW-11, SW-14

**Escopo**

- scheduled saved query execution
- web/API delta retrieval
- retraction/correction alerts
- standing dependency cascade
- report diff
- observation -> candidate -> offline eval -> PR -> canary -> promotion -> rollback

**Critérios de aceite**

- retracted source invalidates affected claims
- unaffected claims remain stable
- no prompt/skill self-edit outside PR
- promotion fails on any regression

## SW-16 — Live swarm evaluation and SOTA benchmark program

**Fase:** P2 — Proof  
**Dependências:** SW-07, SW-09, SW-11, SW-14

**Escopo**

- actual Claude workflow runner in CI/nightly
- single-agent baseline
- independent/centralized/hybrid/team ablations
- agent-count scaling curves
- multi-trial stochastic evaluation
- Kimi replay end-to-end
- DeepResearch Bench/BrowseComp/Silo-Bench/DPBench adapters
- human expert calibration
- cost-quality-latency Pareto

**Critérios de aceite**

- quality superiority statistically significant vs single and Kimi baseline
- no sequential-task regression beyond allowed floor
- reported confidence intervals and cost
- held-out prompts never used for tuning

## SW-17 — CI hardening, supply chain and governance

**Fase:** P2 — Release  
**Dependências:** SW-01, SW-16

**Escopo**

- mypy/pyright blocking
- coverage floor
- property/mutation/fuzz tests
- Linux/macOS/Windows
- plugin marketplace install E2E
- live adapter contract tests
- SBOM, provenance and SLSA-style attestations
- signed tags/releases
- ruleset verification workflow
- release automation

**Critérios de aceite**

- all required checks enforced
- ruleset evidence artifact generated
- reproducible wheel/plugin package
- rollback tested

## SW-18 — Durable multi-tenant swarm backend

**Fase:** P3 — Scale  
**Dependências:** SW-06, SW-13, SW-14

**Escopo**

- stateless orchestrator brains
- durable append-only sessions
- independent sandbox hands
- Postgres/Redis/object store adapters
- horizontal scaling
- tenant quotas/rate limits
- versioned harness and model routing
- rolling/rainbow deployments

**Critérios de aceite**

- 100+ concurrent runs under load
- no cross-tenant leakage
- orchestrator restart loses zero committed state
- cost and latency SLOs


---

# 9. Ordem de execução

```text
P0
SW-00 Native hooks
  → SW-01 Plugin self-contained
  → SW-02 Canonical planner
  → SW-03 Verify-then-seal

P1
SW-04 Role-aware agents
  → SW-05 Unified E2E
      ├→ SW-06 Durable scheduler
      │    ├→ SW-09 Blackboard
      │    └→ SW-14 Observability
      ├→ SW-07 Architecture selector
      │    └→ SW-08 Dynamic replanning
      ├→ SW-10 Context/memory
      └→ SW-11 Semantic epistemics
             └→ SW-12 Report swarm

P2
SW-13 Containment
SW-15 Monitoring/learning
SW-16 Benchmarks
SW-17 Release hardening

P3
SW-18 Durable multi-tenant backend
```

Os quatro primeiros PRs corrigem garantias atualmente inválidas.  
SW-05 cria o primeiro produto realmente unificado.  
SW-07/SW-08/SW-09 são o núcleo de um swarm SOTA.  
SW-16 é o ponto em que “melhor que Kimi” passa de hipótese a afirmação demonstrável.

---

# 10. Benchmark obrigatório

O release SOTA deve comparar, no mesmo conjunto:

1. single strongest agent;
2. independent fan-out;
3. centralized orchestrator;
4. hybrid directed communication;
5. optional Agent Team;
6. Kimi replay/reference.

Medir:

```text
quality:
  task success
  information recall
  citation entailment
  contradiction recall
  calibration
  human preference

coordination:
  integration accuracy
  duplicate work
  message efficiency
  deadlock/contention
  error amplification

systems:
  p50/p95 latency
  tokens
  cost
  retries
  recovery
  critical path
```

O resultado esperado não é “hybrid sempre vence”. O esperado é:

> o architecture selector escolhe corretamente quando não usar swarm e quando usar a topologia apropriada.

---

# 11. CI e prova operacional

A suíte atual precisa crescer para:

```text
unit
contract
property
mutation
fuzz
workflow-static
workflow-live
plugin-install
cross-platform
adapter-live
chaos
benchmark
security-redteam
release-reproducibility
```

Requisitos mínimos:

- mypy/pyright blocking;
- coverage floor;
- live Claude workflow nightly;
- plugin instalado fora do monorepo;
- branch/ruleset verification artifact;
- benchmark report versionado;
- signed release provenance;
- cost regression threshold.

---

# 12. Definition of Done SOTA

O sistema só pode ser chamado SOTA quando:

- hooks validam payload nativo;
- session e run são vinculados sem heurística;
- planner output é exatamente o plan executado;
- custom agents e least privilege são comprovados no trace;
- nenhum artifact é alterado depois do final gate;
- agents paralelos e kernel canônico rodam no mesmo E2E;
- scheduler sobrevive a process/session failure;
- architecture selector evita swarm em tarefas sequenciais;
- replanning responde a gaps e contradições;
- distributed state integration passa benchmarks;
- every material claim possui semantic entailment independente;
- worker containment resiste a prompt injection/SSRF/MCP abuse;
- traces e custo chegam ao nível de claim;
- benchmark mostra ganho estatisticamente significativo e custo conhecido;
- release é reproduzível, cross-platform e governada.

---

# 13. Conclusão

O repositório está muito mais avançado que na auditoria anterior. A fundação Python é valiosa e os Dynamic Workflows provam que você entrou no caminho correto.

O que falta não é volume de arquivos. É **coerência de runtime**:

> o plano, o worker, o state, o evidence graph, o gate e o artifact final precisam pertencer ao mesmo protocolo transacional e observável.

A prioridade absoluta é:

1. corrigir hooks nativos;
2. persistir o plano real;
3. verificar e selar os bytes finais;
4. usar a biblioteca de agentes;
5. unificar JavaScript e Python;
6. tornar o scheduler durável e adaptativo;
7. provar qualidade por benchmark e custo.

Depois desses passos, o KDR-X deixará de ser “um kernel excelente com uma demo de swarm” e passará a ser um verdadeiro sistema de pesquisa multiagente SOTA.
