
# Reauditoria cirúrgica do `rafaelsmc1987/kimiswarm`

**Data:** 19 de agosto de 2026  
**Branch:** `main`  
**Commit:** `37ee7c4e10f7bbf6b2cbc288d16545fb1111f48b`  
**Método:** inspeção estática via GitHub Connector, comparação com os blueprints anteriores e documentação oficial atual do Claude Code.  
**Limitação:** o auditor não executou o código localmente; não existiam GitHub Actions associados ao commit, portanto a afirmação de “70 testes passando” não foi reproduzida nesta sessão.

## Veredito

Você construiu uma fundação real: schemas, DAG compiler, primitives de corpus, BM25 local, modelos claim/evidence, gates básicos, run tree, secret scanner e toy evals.

O produto completo, porém, não está implementado.

- **Fundação offline/determinística:** aproximadamente **68%**.
- **Plano completo:** **35.3%**.
- **Paridade com Kimi:** ainda baixa, porque não há swarm paralelo real.
- **SOTA deep research:** ainda é um MVP offline de primitives.

A prioridade agora não é criar mais schemas. É tornar a execução multiagente real, instalável, bloqueante, retomável e mensurável.

## Matriz de aderência

| Área | Peso | Nota | Status | Diagnóstico |
|---|---:|---:|---|---|
| Higiene e segurança do repositório | 8 | 2.0/10 | **BLOCKER** | Credenciais e artefatos sensíveis continuam versionados; dump da sandbox permanece na raiz; .gitignore insuficiente. |
| Licenças e clean-room | 4 | 7.5/10 | **PARCIAL** | Há matriz e registro clean-room, mas o repo mistura o pacote MIT com material extraído e não possui LICENSE raiz. |
| Schemas e contratos | 8 | 9.0/10 | **FORTE** | Os 15 schemas canônicos existem; falta guidance explícito no AgentBrief e estratégia de migração/versionamento. |
| Planner council e plano executável | 8 | 2.5/10 | **INCOMPLETO** | Existe gate e prompt, mas não há execução real dos cinco planners, reviewer, verifier e synthesizer. |
| DAG compiler | 8 | 7.5/10 | **BOM** | Valida ciclos, deps, owners e self-review; não valida ordem semântica, orçamento total ou ownership por subárvore. |
| Scheduler paralelo e subagents reais | 12 | 1.5/10 | **AUSENTE** | O scheduler é sequencial; max_workers é informativo; não há agent()/pipeline() nem Agent SDK. |
| Plugin/commands/hooks Claude Code | 10 | 2.5/10 | **QUEBRADO** | Manifesto aponta para commands inexistentes, não há workflows, hooks recebem contexto insuficiente e Stop não chama o gate final. |
| Retrieval e corpus | 10 | 3.5/10 | **MVP OFFLINE** | BM25 local e helpers existem; sem web/APIs/dense/PDF/multimodal/citation graph e sem R4 realmente augmentada. |
| Source trust e verificação de citações | 8 | 3.0/10 | **PARCIAL** | Checks locais existem; sem verificação viva de DOI/URL/metadata/retraction e falhas epistemológicas viram WARN. |
| Claim-evidence e contradições | 8 | 4.0/10 | **PARCIAL** | Modelos e standing existem; decomposição é heurística, scores são hard-coded e contradições exigem pares fornecidos. |
| Pipeline de relatório e revisão | 6 | 2.0/10 | **INCOMPLETO** | Há assembler simples; sem writers, rounds, reviewers, fixers, transition editor ou entailment semântico. |
| Estado persistente e resume | 5 | 4.0/10 | **PARCIAL** | Árvore e events existem; manifest não acompanha o run, hashes não são selados e resume não continua o DAG. |
| Compute reproduzível | 3 | 2.0/10 | **SKELETON** | Ledger existe, mas não está integrado e não mantém snapshots/commands/environment suficientes para reprodução. |
| Evals, CI e benchmarks | 8 | 2.0/10 | **INCOMPLETO** | Há toy cases; existe label leakage; não há CI, held-out, benchmarks ou required checks. |
| Monitoring e continuous learning | 4 | 0.5/10 | **AUSENTE** | monitor é placeholder; sem delta retrieval, staleness, alerts ou promotion gate. |

## O que está bem implementado

1. **Schemas:** os 15 modelos prioritários existem e são exportáveis.
2. **DAG compiler:** cobre ciclos, deps, owners, self-review, critical reviewer e tool scope.
3. **Corpus primitives:** URL/DOI normalization, hashes, dedup helpers, source families e BM25.
4. **Claim primitives:** Claim, EvidenceSpan, edges, standing e coverage.
5. **Persistent artifact skeleton:** run dirs, events, manifest, exploration tree, decisions, dead ends e seals.
6. **Clean-room documentation:** há registro e matriz de licenças, embora o escopo precise ser corrigido.

## Blockers
### B-01 — Credenciais vivas e material sensível no Git
**Severidade:** CRITICAL

**Evidência observada**
- `.agent-gw.json`
- `prompts/run_kimi_dir.py`
- `.ssh/authorized_keys`
- `HARs, dotfiles e dumps da sandbox`

**Impacto**
Exposição de contas e impossibilidade de compartilhar/releasear o repo com segurança.

**Correção**
1. Revogar/rotacionar as credenciais antes de qualquer edição Git.
2. Transferir o corpus forense para armazenamento privado e criptografado fora do repo.
3. Remover os paths da árvore e de todo o histórico com git-filter-repo.
4. Invalidar clones antigos e habilitar push protection.
5. Adicionar gitleaks e detect-secrets localmente e em CI.

### B-02 — Plugin KDR-X não é instalável como declarado
**Severidade:** CRITICAL

**Evidência observada**
- `plugin.json referencia commands/*.md`
- `plugins/kdr-x/commands não existe`
- `hooks dependem de cwd/src/Pydantic não garantidos`

**Impacto**
Comandos namespaced e hooks podem não carregar ou falhar em outro projeto.

**Correção**
1. Criar commands/ no plugin ou migrar entrypoints para skills.
2. Criar workflows/ reais.
3. Usar ${CLAUDE_PLUGIN_ROOT} para todos os paths.
4. Fornecer wrapper/bin autocontido e plugin doctor E2E.

### B-03 — Hooks de lifecycle não executam os gates prometidos
**Severidade:** CRITICAL

**Evidência observada**
- `TaskCreated e TaskCompleted não estão registrados`
- `.claude Stop não tem state completo`
- `kdr-hook Stop chama hook_pre_tool_use`
- `SubagentStop espera objetos custom que não vêm no payload nativo`

**Impacto**
Claude pode parar/entregar com DAG incompleto, claims não resolvidos e sem DeliveryManifest.

**Correção**
1. Criar hooks/hooks.json compatível com o payload oficial.
2. Consumir stdin real por evento.
3. Registrar TaskCreated, TaskCompleted, SubagentStop e Stop.
4. Descobrir o active run no Stop e executar hook_stop de verdade.
5. Testar o wrapper como subprocess com exit code 2.

### B-04 — Não existe swarm paralelo executável
**Severidade:** CRITICAL

**Evidência observada**
- `WaveScheduler usa for sequencial`
- `max_workers não despacha concorrência`
- `não há workflows JavaScript`
- `não há chamadas agent()/pipeline()`

**Impacto**
Não reproduz a característica central do Kimi Swarm.

**Correção**
1. Implementar Dynamic Workflows JavaScript como control plane.
2. Usar Python para schemas/state/gates, não como substituto dos agents.
3. Separar workflow de plan e execute.
4. Executar cada wave com pipeline() e resultados estruturados.

### B-05 — CLI principal possui comandos quebrados/no-op
**Severidade:** HIGH

**Evidência observada**
- `run é mapeado para cmd_demo com argumentos incompatíveis`
- `verify só imprime`
- `report só imprime`
- `monitor é placeholder`
- `plan não existe`

**Impacto**
A superfície prometida na documentação não corresponde ao comportamento real.

**Correção**
1. Adicionar cmd_plan.
2. Implementar cmd_run carregando plan/manifest.
3. Implementar verify/report reais.
4. Implementar monitor ou removê-lo do release.
5. Adicionar testes subprocess para todos os commands.

### B-06 — Gates epistemológicos não bloqueiam
**Severidade:** HIGH

**Evidência observada**
- `source_trust usa warn_is_pass=True`
- `citation_integrity usa warn_is_pass=True`
- `teste E2E aceita pass ou warn`
- `empty corpus retorna sucesso`

**Impacto**
Runs fracos ou sem evidência útil podem ser classificados como sucesso.

**Correção**
1. Adicionar severidade blocking/advisory por check.
2. Existência/identidade/span/claim material devem bloquear.
3. COI/currency podem ser advisory conforme risk policy.
4. Aplicar política por route e risk level.

### B-07 — Sem CI, branch protection ou prova independente dos testes
**Severidade:** HIGH

**Evidência observada**
- `zero workflow runs associados ao commit`
- `main sem proteção/required checks`
- `commit unsigned e autoria placeholder`

**Impacto**
Regressões e secrets entram diretamente em main.

**Correção**
1. Adicionar CI/security/plugin-e2e/evals workflows.
2. Habilitar branch protection e required checks.
3. Exigir PR/review.
4. Corrigir user.name/user.email e assinar commits quando possível.


# Análise por componente

## Segurança e separação do repositório

O repositório ainda contém credenciais não redigidas, `.ssh/authorized_keys`, HARs, dotfiles, PIDs, caches e dumps de runtime/home. A `.gitignore` só cobre artefatos Python e `.research/`.

O pacote `src/kdrx` pode ser MIT, mas o repositório inteiro não deve ser apresentado como um artefato MIT homogêneo enquanto contiver material extraído de terceiros. O corpus forense deve ficar fora do repositório de produto, com apenas um manifesto sanitizado e hashes.

Target:

```text
kimiswarm/
├── src/kdrx/
├── plugins/kdr-x/
├── tests/
├── docs/
└── evidence-manifest/       # índice sanitizado, sem bytes sensíveis

forensic-corpus/              # storage privado separado
```

## README, licença e governança

Falhas:

- README raiz descreve “Kimi Thinking Prefill”, não KDR-X.
- não há `LICENSE` raiz;
- não há `SECURITY.md`;
- autoria Git está como placeholder;
- commit não assinado;
- `main` não protegida;
- nenhum required status check.

## Plugin Claude Code

### Paths inexistentes

`plugin.json` declara `commands/plan.md`, `commands/run.md` etc., mas `plugins/kdr-x/commands/` não existe. Os arquivos em `.claude/commands/kdr/` pertencem ao projeto, não ao pacote do plugin.

### Sem Dynamic Workflows

Não existe `workflows/`. Portanto os arquivos Markdown descrevem uma orquestração, mas não a codificam. Claude ainda decide turno a turno.

### Hooks não portáveis

O project setting usa path relativo e pressupõe `src/` + Pydantic. O plugin instalado em outro repo não tem essas garantias.

O inline hook do manifest fabrica um JSON vazio em vez de consumir o payload real do stdin. O wrapper de `Stop` não chama `hook_stop`; chama uma checagem noop de PreToolUse.

Target:

```text
plugins/kdr-x/
├── .claude-plugin/plugin.json
├── workflows/
│   ├── kdr-plan.js
│   ├── kdr-run.js
│   ├── kdr-verify.js
│   └── kdr-deep-research.js
├── commands/
├── skills/
├── agents/
├── hooks/hooks.json
├── bin/
└── schemas/
```

## Planner council

Há apenas um prompt dizendo para executar cinco perspectivas. `planner.py` valida um plano já pronto, mas não cria nem coordena:

- requirements planner;
- scope planner;
- retrieval planner;
- methodology planner;
- risk planner;
- reviewer;
- verifier;
- synthesizer.

O planner deve ser um workflow JavaScript com fan-out real e schemas.

## DAG e scheduler

O DAG compiler é uma boa base. O scheduler, porém, executa:

```python
for tid in ready:
    self._run_task(...)
```

Logo é sequencial.

Há uma race escondida: `T-VERIFY` não depende de `T-RETRIEVE`; ambos ficam na wave 0. Hoje funciona apenas porque o scheduler percorre a lista na ordem. Em concorrência real, verify pode iniciar sem sources.

Correção imediata:

```python
TaskSpec(
    task_id="T-VERIFY",
    dependencies=["T-RETRIEVE"],
)
```

Waves devem ser derivadas das dependencies, nunca usadas como substituto delas.

## CLI

- `kdr run` está mapeado para `cmd_demo`, mas os argumentos do parser são incompatíveis.
- `kdr verify` só imprime o manifest.
- `kdr report` só lê um arquivo.
- `kdr monitor` é placeholder.
- `kdr plan` não existe.

A CLI deve implementar operações reais e testes subprocess.

## Retrieval

Estado atual:

- apenas BM25 local;
- QueryGraph não integrado;
- saturation não integrada;
- sem web/APIs;
- sem dense;
- sem PDF/HTML completo;
- sem multimodal/cross-lingual;
- R4 declarada sem augmentation.

O EvidenceSpan não é verbatim: o texto é tokenizado, normalizado e juntado novamente, perdendo casing, pontuação, whitespace e locator. Deve preservar offsets no texto original.

## Source trust

Os checks locais verificam a presença de metadata, não a existência real da fonte.

Bugs:

- `currency_check` não entra no gate;
- gate converte falhas em WARN;
- FileCorpus não preenche content hash;
- Markdown vira SourceType.UNKNOWN;
- pipeline segue em frente.

Target:

```text
source identity
→ metadata match
→ version/retraction
→ domain policy
→ quality/independence
→ claim entailment
```

## Claims e standing

`compute_standing()` é uma boa primitive, mas o runner:

- não usa o semantic decomposer;
- cria claims de qualquer sentence com número;
- grava quality/independence/confidence hard-coded;
- não executa entailment;
- não possui calibration dataset.

A pontuação parece científica, mas hoje deriva de constantes.

## Contradição e falsificação

Existe um plano de papéis, mas não sua execução. O detector não encontra semanticamente os pares.

O eval de contradição lê os pares a partir do próprio gold/expected e os entrega ao detector. Isso é label leakage. Gold labels nunca podem entrar no input do detector.

## Reporting

O report atual é uma lista determinística; o próprio result diz que não há LLM writer.

Faltam:

- outline council;
- section DAG;
- writers;
- section reviewers;
- fixers;
- transition editor;
- conclusion tardia;
- citation manager;
- artifact conversion.

O integrity gate usa WARN, não detecta material claims omitidos, não verifica entailment semântico e pode listar references não citadas.

## State e resume

O scaffold existe, mas:

- o default não segue `.research/runs/<id>`;
- manifest não muda de PENDING;
- completed/failed/gates/hashes não são persistidos;
- resume não continua tasks;
- active run não é acessível ao Stop hook;
- writes não usam safe_join.

## Compute

O ledger passa hashes ao runner como se fossem o conteúdo original. Para reproduzir, é necessário registrar snapshot/URI, content hash, script+hash, environment lock, seed, command, outputs e logs.

## Evals e CI

Existem apenas casos toy. Faltam held-out, hard negatives, multi-trial, calibration, report/retrieval metrics, benchmark adapters e GitHub Actions.

O regression gate atual usa mean recall. Deve exigir per-kind precision/recall/F1, zero critical miss e thresholds versionados.

# Plano de correção por PRs

## PR-00 — Emergency security and repository split
**Prioridade:** P0
**Dependências:** nenhuma

**Objetivo**
Eliminar exposição e separar produto de evidência forense.

**Mudanças**
1. Revogar credenciais.
2. Arquivar material forense fora do repo.
3. Reescrever histórico com git-filter-repo.
4. Expandir .gitignore.
5. Adicionar README, LICENSE com escopo, SECURITY e secret scanners.

**Testes**
- gitleaks no working tree e histórico
- detect-secrets
- forbidden-path test

**Gate**
Zero secret; nenhum .ssh/.agent-gw/HAR/dump na árvore de produto.

## PR-01 — Plugin packaging and CLI correctness
**Prioridade:** P0
**Dependências:** PR-00

**Objetivo**
Fazer plugin e CLI corresponderem ao manifesto.

**Mudanças**
1. Criar commands/ ou converter para skills.
2. Adicionar bin/kdr-hook com CLAUDE_PLUGIN_ROOT.
3. Mover hooks para hooks/hooks.json.
4. Corrigir stdin/payload.
5. Adicionar cmd_plan e corrigir run/verify/report/monitor.
6. Criar plugin doctor.

**Testes**
- manifest path test
- CLI subprocess suite
- hook stdin E2E
- temp repo plugin smoke

**Gate**
Plugin doctor sem warnings; todos os entrypoints funcionam ou falham explicitamente.

## PR-02 — Real Claude Code Dynamic Workflows
**Prioridade:** P0
**Dependências:** PR-01

**Objetivo**
Transformar Markdown em orquestração executável.

**Mudanças**
1. Adicionar kdr-plan.js, kdr-run.js, kdr-verify.js e kdr-deep-research.js.
2. Fan-out de cinco planners.
3. Waves com pipeline().
4. Schema em toda saída.
5. Retry/null/no-progress e gate entre waves.
6. Persistir paths e outputs reais.

**Testes**
- workflow syntax
- concorrência real
- dependency ordering
- null/retry/no-progress

**Gate**
Demonstração com 4+ agents independentes, 2+ waves e gate final.

## PR-03 — Agent library and Kimi contract parity
**Prioridade:** P1
**Dependências:** PR-02

**Objetivo**
Adicionar papéis-base e briefing guidance/context/mission.

**Mudanças**
1. Adicionar general/coder/explore/plan/reviewer/verifier.
2. Adicionar especialistas de search/evidence/claims/writing.
3. Adicionar guidance ao AgentBrief.
4. Definir tools, disallowedTools, maxTurns, effort, skills e background.
5. Mover agents que exigem controles fortes para .claude/agents.
6. Usar worktree para editores de código.

**Testes**
- frontmatter lint
- read-only policy
- role resolution
- independent reviewer

**Gate**
Toda TaskSpec resolve para agent existente e briefing autocontido.

## PR-04 — State machine, resume and hard gates
**Prioridade:** P1
**Dependências:** PR-02, PR-03

**Objetivo**
Persistir execução real e permitir retomada.

**Mudanças**
1. Padronizar .research/runs/<id>.
2. Atualizar manifest a cada transição.
3. Persistir attempts/results/gates/hashes.
4. Reconstruir ready queue.
5. Atomic writes/locks.
6. Criar DeliveryManifest e open test.
7. Separar advisory/blocking.

**Testes**
- crash/restart por wave
- hash mismatch
- fault injection
- Stop gate

**Gate**
Resume não repete tasks fechadas e preserva provenance.

## PR-05 — Production retrieval and corpus
**Prioridade:** P1
**Dependências:** PR-04

**Objetivo**
Implementar R0–R4 de verdade.

**Mudanças**
1. Adapters WebSearch/WebFetch/GitHub/APIs oficiais/scholarly.
2. Integrar QueryGraph.
3. Rank fusion lexical+dense+source-specific.
4. Exact char spans e locators.
5. Extractors PDF/HTML/Markdown/code.
6. Integrar dedup/dependency families.
7. Usar evidence saturation.

**Testes**
- retrieval benchmark
- span fidelity
- canonicalization
- syndication collapse
- route C/D

**Gate**
Recall/diversidade superam BM25 baseline; spans são realmente verbatim.

## PR-06 — Source trust chain
**Prioridade:** P1
**Dependências:** PR-05

**Objetivo**
Verificar fontes externamente e com policies por domínio.

**Mudanças**
1. HTTP/DOI resolver.
2. Crossref/OpenAlex/Semantic Scholar e cache.
3. Retraction/version/date.
4. Policy registry.
5. COI/primaryness/directness/independence separados.
6. Incluir currency no gate.
7. Critical fail bloqueia.

**Testes**
- fabricated DOI
- DOI misdirection
- metadata mismatch
- retraction
- stale cache
- API outage

**Gate**
Seeded citation defects atingem thresholds sem label leakage.

## PR-07 — Semantic claims, contradictions and falsification
**Prioridade:** P1
**Dependências:** PR-06

**Objetivo**
Remover heurísticas/scores arbitrários.

**Mudanças**
1. Claim decomposer estruturado.
2. Independent entailment verifier.
3. Todas as relações de edge.
4. Automatic contradiction discovery.
5. Falsification swarm.
6. Standing por edge auditável.
7. Unresolved registry/disclosure.

**Testes**
- compound decomposition
- partial support
- scope/time mismatch
- counterevidence
- calibration

**Gate**
Todo claim material possui edge auditável e julgamento independente.

## PR-08 — Report swarm and final integrity
**Prioridade:** P2
**Dependências:** PR-07

**Objetivo**
Implementar pipeline editorial completa.

**Mudanças**
1. Outline council.
2. Section DAG e one-section-per-task.
3. Evidence packs mínimos.
4. Section reviewers/fixers/transition editor.
5. Summary/conclusion tardios.
6. Citation manager/assembler.
7. Hard final integrity.
8. References só citadas.

**Testes**
- chapter rounds
- orphan/dangling citations
- omitted material claim
- unresolved disclosure
- UTF-8/open test

**Gate**
Relatório passa reviewer independente e Claim→Evidence→Source trace.

## PR-09 — Evals, CI and branch protection
**Prioridade:** P1
**Dependências:** PR-01

**Objetivo**
Provar qualidade e bloquear regressões.

**Mudanças**
1. Eliminar label leakage.
2. Gold/dev/held-out.
3. Precision/recall/F1/calibration por defect.
4. CI Python/lint/type/security/plugin/evals.
5. Adapters DeepResearch Bench II e replay Kimi.
6. Branch protection.

**Testes**
- Python 3.10–3.13
- multi-trial
- held-out
- regression baseline

**Gate**
Main só recebe merge com checks e thresholds aprovados.

## PR-10 — Monitoring and governed learning
**Prioridade:** P2
**Dependências:** PR-06, PR-09

**Objetivo**
Implementar monitoramento e aprendizagem controlada.

**Mudanças**
1. Saved queries/delta retrieval.
2. Retraction/correction alerts.
3. Standing recompute.
4. Report diffs.
5. Observation→candidate→eval→approval→canary→promotion.

**Testes**
- delta source
- retraction invalidation
- stale cache
- promotion regression

**Gate**
Atualizações externas afetam somente dependências e learning nunca promove sem eval.


# Ordem crítica

```text
PR-00 Security
  ↓
PR-01 Plugin/CLI
  ↓
PR-02 Dynamic Workflows
  ↓
PR-03 Agent contracts
  ↓
PR-04 State/resume
  ↓
PR-05 Retrieval
  ↓
PR-06 Source trust
  ↓
PR-07 Claims/falsification
  ↓
PR-08 Report swarm

PR-09 CI/evals começa logo após PR-01 e cresce em paralelo.
PR-10 Monitoring vem depois de source trust + evals.
```

# Definition of Done corrigida

O plano só estará concluído quando:

- zero credential no working tree e histórico;
- plugin instala em repo vazio;
- workflows JavaScript executam agents reais;
- planner council realmente lança cinco planners;
- waves executam em paralelo e respeitam deps;
- briefing contém guidance/context/mission;
- routes que exigem web usam adapters reais;
- EvidenceSpan preserva texto original e locator;
- source identity é verificada externamente;
- claim edges passam por verifier independente;
- contradiction detector não recebe labels;
- writers e reviewers são diferentes;
- final integrity bloqueia;
- state/resume continua o DAG;
- monitor não é placeholder;
- CI e branch protection estão ativos;
- benchmarks de regressão passam;
- documentação não promete funcionalidades ausentes.

# Conclusão

Você não deixou de fazer tudo. Construiu uma base técnica organizada.

O ponto de retomada é:

> parar de adicionar primitives e transformar as primitives em uma execução multiagente real, instalável, bloqueante, retomável e mensurável.

- Depois de **PR-02**, o projeto começa a se comportar como Kimi Swarm.
- Depois de **PR-07**, começa a ter chance de superar o Kimi epistemologicamente.
- Depois de **PR-09**, isso pode ser demonstrado de forma reproduzível.
