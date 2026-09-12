# Auditoria de evidências — kimiswarm

Data: **2026-09-11**. Branch observada: **main**. Commit: **`2e2851d820cbed7060064a6584e7eb7f26b25885`**.

## Escopo e limites

Esta é uma auditoria estática com inspeção do CI histórico, não uma execução live. A cobertura integral/parcial por arquivo está em `COBERTURA_AUDITORIA.json`. Não foi possível clonar/executar o repositório no ambiente desta sessão. Os bundles binários, todos os scripts/testes e o histórico completo não foram auditados. Nenhuma alteração foi feita no GitHub.

O job [pytest (py3.12)](https://github.com/rafaelsmc1987/kimiswarm/actions/runs/32350435653/job/96368225974) de 20/08/2026 registra **368 testes aprovados em 41,95 s** no SHA acima. Isso é evidência de um CI real, não dos 160 novos cenários propostos, nem de agentes live. A execução de governança consultada em 11/09/2026 não substitui um novo E2E.

## Parecer

Há um núcleo offline real e aproveitável. O risco principal é a distância entre contratos/heurísticas determinísticos e um sistema multiagente live durável: plano, permissões, estado, evidência e entrega precisam de uma autoridade comum. O caminho é integração progressiva com testes de comportamento, não reescrever tudo nem aumentar agentes por padrão.

SW-00 a SW-03 constam como concluídos no registro histórico; SW-04 a SW-18 continuam pendentes naquele mesmo registro. A nova decomposição KS preserva o trabalho válido e acrescenta correções e provas mais fortes. Não recalcula a nota histórica de 48,1 e não a apresenta como medição atual.

## Achados


### F-01 — Scheduler sequencial e validação incompleta do resultado

**Prioridade:** P0 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** O loop de tarefas é sequencial. A validação checa cobertura dos nomes de outputs e quantidade de evidence_refs, mas não a identidade da tarefa nem bytes, schema ou execução dos testes declarados.

**Consequência:** Concorrência não decorre de max_workers; uma declaração do executor pode ser aceita sem artefato válido.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-008, KS-023, KS-024, KS-027, KS-028, KS-029

**Fontes fixadas no commit:** [src/kdrx/scheduler.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/scheduler.py); [src/kdrx/schemas/plan.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/schemas/plan.py)


### F-02 — Retomada parcial não reidrata o executor

**Prioridade:** P0 · **Evidência:** CAMINHO_DE_CODIGO_INSPECIONADO

**Observação:** resume_run pré-completa tarefas e cria executor com listas vazias; _verify exige sources. O teste examinado retoma um run inteiramente concluído, não a fronteira após T-RETRIEVE.

**Consequência:** Uma retomada parcial pode bloquear ou perder insumos já persistidos. A CLI já bloqueia hash mismatch; essa proteção deve ser preservada.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-002, KS-007, KS-020, KS-021, KS-072

**Fontes fixadas no commit:** [src/kdrx/runner.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/runner.py); [tests/test_phase4_resume.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/tests/test_phase4_resume.py); [src/kdrx/cli.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/cli.py)


### F-03 — Dois caminhos de execução sem autoridade comum

**Prioridade:** P0 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** O executor Python despacha quatro IDs fixos; o JavaScript pede a agentes para ler e executar uma representação reduzida do plano. O deep-research sintetiza waves em memória.

**Consequência:** Papéis, ferramentas, orçamento e estado podem divergir entre o plano persistido e a execução.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-010, KS-023, KS-024, KS-025, KS-026, KS-034

**Fontes fixadas no commit:** [plugins/kdr-x/workflows/kdr-run.js](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/plugins/kdr-x/workflows/kdr-run.js); [plugins/kdr-x/workflows/kdr-deep-research.js](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/plugins/kdr-x/workflows/kdr-deep-research.js); [src/kdrx/runner.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/runner.py)


### F-04 — Semânticas distintas de verify, seal e entrega

**Prioridade:** P0 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** cmd_verify reporta plan_dag, mas não o inclui em all_pass. cmd_seal inclui DAG e deixa claims críticas não resolvidas para o Stop hook. O hash conferido e o emitido por seal_delivery podem vir de leituras distintas.

**Consequência:** É preciso separar integridade, aptidão para entrega e estado de conclusão, além de eliminar a janela entre verificação e releitura. O selo pós-relatório já existe: não é uma funcionalidade ausente.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-011, KS-012, KS-062

**Fontes fixadas no commit:** [src/kdrx/cli.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/cli.py); [src/kdrx/runner.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/runner.py)


### F-05 — Identidade, locks e registry insuficientes para múltiplos processos

**Prioridade:** P0 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** run_id usa segundos e slug; RunState concatena run_id com root. Há lock por instância e read-modify-write de JSON; o registry tolera corrupção retornando vazio.

**Consequência:** Risco de colisão, perda de atualização, cruzamento de sessão ou recuperação ambígua sob concorrência. safe_join nas operações de arquivo é uma proteção útil já existente.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-009, KS-020, KS-021, KS-030

**Fontes fixadas no commit:** [src/kdrx/state.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/state.py); [src/kdrx/native_hooks.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/native_hooks.py)


### F-06 — Parser de citação não aceita todos os IDs emitidos

**Prioridade:** P0 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** O regex de citações aceita letras, números, ponto, hífen, underscore e dois-pontos; IDs de fonte podem conter barras, espaços ou URL.

**Consequência:** Uma referência válida para o registry pode ser invisível ao parser. Padronizar IDs opacos e separar URI evita dependência de nomes de arquivo.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-013, KS-057, KS-061

**Fontes fixadas no commit:** [src/kdrx/reporting.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/reporting.py); [src/kdrx/retrieval.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/retrieval.py); [src/kdrx/adapters.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/adapters.py)


### F-07 — Claim ligada ao último span da fonte

**Prioridade:** P0 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** _extract_claims usa um dicionário source_id -> span que retém só um trecho por fonte; claims do mesmo documento recebem esse trecho, independentemente da posição da frase.

**Consequência:** Proveniência ao nível do documento é confundida com suporte textual exato.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-014, KS-049, KS-050

**Fontes fixadas no commit:** [src/kdrx/runner.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/runner.py)


### F-08 — Cobertura e counterevidence não representam a evidência exigida

**Prioridade:** P1 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** Cobertura de termos do objetivo é passada como critical_claim_coverage; unresolved_blockers é zero nesse cálculo. Counterevidence é persistida, mas não participa diretamente das arestas calculadas no trecho inspecionado.

**Consequência:** A pesquisa pode parar por aproximação lexical, e a refutação encontrada não necessariamente muda o standing.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-015, KS-016, KS-044, KS-055, KS-067, KS-068

**Fontes fixadas no commit:** [src/kdrx/runner.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/runner.py)


### F-09 — Entailment lexical, não semântico

**Prioridade:** P1 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** entailment_score mede sobreposição de tokens e consistência de números; não verifica a implicação semântica. Escopo temporal compara o ano da publicação com o da claim.

**Consequência:** Negação, população, evento passado e relação causal podem ser interpretados incorretamente.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-049, KS-050, KS-051, KS-052, KS-056

**Fontes fixadas no commit:** [src/kdrx/claims.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/claims.py)


### F-10 — Cobertura do relatório restrita a claims registradas e heurísticas

**Prioridade:** P1 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** Parte dos gates usa presença literal das claims e um detector de sentenças quantitativas. Novas afirmações qualitativas não registradas exigem extração/verificação adicional.

**Consequência:** Aprovar referências ou substrings não garante que todas as afirmações materiais tenham suporte.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-057, KS-059, KS-060, KS-061, KS-062

**Fontes fixadas no commit:** [src/kdrx/reporting.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/reporting.py)


### F-11 — Busca e edição offline são heurísticas úteis, não agentes live

**Prioridade:** P1 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** O canal dense padrão é char-ngram cosine, explicitamente não neural. O report swarm determinístico separa classes, mas não demonstra escritores/revisores LLM independentes.

**Consequência:** Preservar esses componentes como baseline e testar ganhos reais com retrieval semântico e pipeline editorial vivo.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-042, KS-059, KS-060, KS-074, KS-076

**Fontes fixadas no commit:** [src/kdrx/retrieval.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/retrieval.py); [src/kdrx/reporting.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/reporting.py)


### F-12 — Egress não impede SSRF/redirecionamento inseguro

**Prioridade:** P0 · **Evidência:** RISCO_DE_CONTROLE_INSPECIONADO

**Observação:** A policy valida o host inicial e o transporte urllib segue requisições/redirecionamentos sem proteção de IP privado explícita no código examinado. A leitura da resposta não tem limite de bytes.

**Consequência:** Antes de rede real, exigir validação de protocolo/host/IP a cada hop, limites de tamanho e um broker de ferramentas/credenciais.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-017, KS-031, KS-035, KS-039

**Fontes fixadas no commit:** [src/kdrx/adapters.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/adapters.py); [src/kdrx/security.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/security.py)


### F-13 — Contratos de adapters e dependências exigem hardening

**Prioridade:** P1 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** OpenAlex pode chamar .get em source=null; Crossref reduz data ao primeiro dia do ano. Markdown remove code fences; PDF concatena páginas e depende de pypdf opcional.

**Consequência:** Falhas de payload, perda de precisão e conteúdo relevante descartado prejudicam pesquisa real. A ausência de pypdf já gera erro explícito e não foi tratada como extração fictícia.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-005, KS-035, KS-036, KS-037, KS-040, KS-041

**Fontes fixadas no commit:** [src/kdrx/adapters.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/adapters.py); [src/kdrx/extractors.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/extractors.py); [pyproject.toml](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/pyproject.toml)


### F-14 — Cálculo recebe hashes onde o contrato fala em conteúdos

**Prioridade:** P1 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** Calculation.inputs é descrito como nome -> hash; reproducible_from entrega esse mapa ao runner, cujo contrato descreve conteúdos. Script e unit_checks são registrados, não executados por essa função.

**Consequência:** A reproducibilidade precisa resolver blobs por hash, executar transformação versionada e conferir resultados e unidades.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-051, KS-063

**Fontes fixadas no commit:** [src/kdrx/analysis.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/analysis.py)


### F-15 — Licenças e disponibilidade dos plugins externos não resolvidas

**Prioridade:** P0 · **Evidência:** METADADOS_INSPECIONADOS

**Observação:** A MIT da raiz tem escopo delimitado. scholar declara UNLICENSED. O script de imagem resolve latest.url e instala wheel por pip --user; acesso ao gateway e autorização de redistribuição não foram comprovados.

**Consequência:** Não liberar esses componentes como parte do produto por presunção. Auditar cada licença/SDK e disponibilizar alternativas com contrato documentado.

**Limite:** Não é conclusão jurídica sobre titularidade ou ilicitude. É uma pendência de proveniência, autorização e disponibilidade operacional.

**Tratamento:** KS-004, KS-045, KS-046, KS-047, KS-078

**Fontes fixadas no commit:** [LICENSE](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/LICENSE); [docs/LICENSE_MATRIX.md](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/docs/LICENSE_MATRIX.md); [plugins/scholar/kimi.plugin.json](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/plugins/scholar/kimi.plugin.json); [plugins/image_generation/scripts/image_generation_tool.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/plugins/image_generation/scripts/image_generation_tool.py)


### F-16 — CI real, porém sem prova do swarm live

**Prioridade:** P1 · **Evidência:** LOG_HISTORICO_E_TESTES_INSPECIONADOS

**Observação:** O log do job 96368225974 registra 368 passed in 41.95s no SHA auditado. test_workflows declara validação estrutural, com AsyncFunction e checagens de marcadores, não execução real do host.

**Consequência:** Preservar a suíte e acrescentar golden runs live, instalação limpa, falhas injetadas, testes de comportamento e comparação externa.

**Limite:** Não houve execução local da suíte nesta sessão. O resultado de 368 testes pertence ao CI de 20/08/2026.

**Tratamento:** KS-001, KS-002, KS-034, KS-071, KS-072, KS-073, KS-074, KS-075

**Fontes fixadas no commit:** [tests/test_workflows.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/tests/test_workflows.py); [tests/test_phase4_resume.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/tests/test_phase4_resume.py); [README.md](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/README.md)


### F-17 — Status de ciclos históricos não demonstra produto concluído

**Prioridade:** P1 · **Evidência:** DOCUMENTACAO_E_COMMIT_INSPECIONADOS

**Observação:** O README contém 234 testes e checklist de 81/81 de outro ciclo. STATUS marca SW-00..03 DONE e SW-04..18 PENDENTE no commit que permanece em main.

**Consequência:** Gerar matriz de capacidades por backend/SHA, sem confundir tarefas antigas concluídas com superioridade científica ou integração live.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-001, KS-006, KS-079

**Fontes fixadas no commit:** [README.md](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/README.md); [auditoria/sota-2026-08-19/STATUS.md](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/auditoria/sota-2026-08-19/STATUS.md); [auditoria/sota-2026-08-19/ROADMAP_SOTA_SWARM.json](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/auditoria/sota-2026-08-19/ROADMAP_SOTA_SWARM.json)


### F-18 — Compilação do DAG tem proteções, mas precisa de limites e normalização

**Prioridade:** P1 · **Evidência:** CODIGO_INSPECIONADO

**Observação:** O DAG valida dependências, ownership e self-review. DFS e cálculo de waves são recursivos; aliases de caminhos e serialização manual precisam de testes. Canonicalização elimina query parameters genéricos.

**Consequência:** Evitar overflow em DAG profundo e colisões de artefatos; não colapsar URLs de conteúdos distintos.

**Limite:** Achado de leitura estática; não houve reprodução contra um checkout local nesta sessão.

**Tratamento:** KS-003, KS-009, KS-019, KS-022, KS-032, KS-043, KS-072

**Fontes fixadas no commit:** [src/kdrx/dag.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/dag.py); [src/kdrx/corpus.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/corpus.py); [src/kdrx/artifact.py](https://github.com/rafaelsmc1987/kimiswarm/blob/2e2851d820cbed7060064a6584e7eb7f26b25885/src/kdrx/artifact.py)


## Referências externas primárias

- **EXT-01** [Claude Code — Workflows](https://code.claude.com/docs/en/workflows) — Contrato e limites atuais do host; não confundir workflow com um runtime JavaScript genérico. Consultada em 2026-09-11.

- **EXT-02** [Claude Code — Hooks reference](https://code.claude.com/docs/en/hooks) — Conferência do formato de hooks nativos; command/args não foi tratado como defeito. Consultada em 2026-09-11.

- **EXT-03** [Claude Code — Plugins reference](https://code.claude.com/docs/en/plugins-reference) — Conferência do manifesto e suporte a workflows. Consultada em 2026-09-11.

- **EXT-04** [Moonshot AI — Kimi K2.5](https://www.kimi.ai/blog/kimi-k2-5) — Referência histórica do swarm original e do PARL; não é afirmação sobre o modelo mais recente em setembro de 2026. Consultada em 2026-09-11.

- **EXT-05** [DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents](https://arxiv.org/abs/2506.11763) — Identificador inequívoco do benchmark; não confundir com outros trabalhos de nome semelhante. Consultada em 2026-09-11.

- **EXT-06** [SQLite — Write-Ahead Logging](https://sqlite.org/wal.html) — Limites de concorrência/durabilidade e correção WAL-reset; verificar a biblioteca efetivamente instalada. Consultada em 2026-09-11.

- **EXT-07** [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — Referência para controles de rede e redirecionamento. Consultada em 2026-09-11.
