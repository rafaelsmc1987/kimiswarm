# Blockers críticos — KimiSwarm SOTA

## S0-01 — Hooks usam payload KDR-X customizado, não o payload nativo do Claude Code

**BLOCKER**

Os hooks mais importantes podem falhar com KeyError ou não validar a task/agent real; a conclusão 18/18 não prova enforcement no harness nativo.

### Correções

- Criar NativeHookEnvelope por evento e adapters específicos.
- Persistir session_id -> run_id e task_id nativo -> TaskSpec canônico.
- Extrair AgentResult do transcript/result artifact no SubagentStop.
- Emitir JSON/event-specific decision e stderr compatíveis com Claude Code.
- Cobrir stop_hook_active, recursive stop e ausência de active run.
- Executar contract tests contra fixtures copiadas da documentação oficial.

## S0-02 — Split-brain entre plano do planner council e plan.json executado

**BLOCKER**

As cinco perspectivas podem não controlar o DAG executado; o sistema apresenta planner council sem executar suas decisões.

### Correções

- Usar JSON Schema canônico exportado pelo Python no workflow.
- Adicionar kdr import-plan --run-dir ... --stdin e validar compile_dag + plan_gate.
- Persistir plan revision, plan hash, provenance dos planners e approval.
- Bloquear se review.approved=false; implementar revisão/correção até PASS.
- Nunca aceitar um plano compacto sem role/tools/skills/guidance/context/owner/reviewer/acceptance/retry/budget.

## S0-03 — Relatório final é escrito depois da verificação

**BLOCKER**

O artefato entregue não é necessariamente o artefato que passou nos gates; uma escrita pós-gate invalida toda garantia de integridade.

### Correções

- Ordenar: draft -> review/fix -> assemble -> verify -> seal -> immutable delivery.
- Proibir qualquer Write/Edit no artifact sealed.
- Gravar verified_report_hash no DeliveryManifest.
- Stop hook deve comparar hash atual com o hash verificado.
- Executar final verifier sobre o relatório exatamente entregue.

## S0-04 — A biblioteca de agentes não é usada pela orquestração

**BLOCKER**

Não há garantia de especialização, least privilege, model routing, worktree, effort ou skills; muitos agentes definidos podem nunca carregar.

### Correções

- Corrigir manifest para auto-discovery de agents/ ou paths './agents/'.
- Gerar AgentExecutionSpec por TaskSpec com agent_type, model, effort, cwd, tools, worktree e schema.
- Invocar explicitamente os agentes resolvidos em vez de persona textual.
- Mover controles não suportados por plugin para .claude/agents ou policy global.
- Adicionar doctor que compara AgentRole enum, role-resolution e agents realmente carregados por `claude agents`.

## S0-05 — Não existe um único E2E que una agentes reais e o kernel canônico

**BLOCKER**

Cada metade demonstra algo diferente; nenhuma prova o produto SOTA completo.

### Correções

- Definir o Python como control API/sidecar determinístico e o workflow como executor.
- Toda task deve fazer claim/lease via API, receber AgentBrief canônico e commit de AgentResult.
- Integrar adapters, source trust, claim graph, report swarm e gates no mesmo run.
- Criar uma golden E2E com web real, múltiplos agentes, conflito, retry, resume e relatório sealed.

## S0-06 — Stop hook não é session-bound e pode escolher o run errado

**HIGH**

Uma sessão pode ser bloqueada/liberada com base em outro run, em gates obsoletos ou sem claims críticos reais.

### Correções

- Criar session registry persistente session_id -> run_id.
- Nunca usar most-recent-directory como fonte de verdade.
- Carregar DeliveryManifest persistido, verificar seals e unresolved registry.
- Exigir gate timestamps/hash posteriores ao relatório final.

## S0-07 — Branch protection declarada não é confirmada pela API clássica

**HIGH**

A governança pode estar documentada de forma incorreta, ter sido removida ou existir apenas em ruleset não auditado.

### Correções

- Consultar e exportar repository rulesets como artifact de CI.
- Adicionar governance-verification workflow que falha quando proteção/ruleset diverge.
- Atualizar README para distinguir classic branch protection de rulesets.
- Adotar signed tags/releases e, se viável, signed commits.
