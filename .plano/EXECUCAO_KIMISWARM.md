# Registro de execução do plano

Os três documentos originais foram preservados. Este registro descreve a implementação parcial e suas lacunas; não encerra o backlog.

Baseline: 368 testes aprovados. Implementação: 514 aprovados, 0 falhos, 0 erros, 0 ignorados.

Cenários do backlog aprovados no escopo local e vinculados ao JUnit: 14. Isso não certifica as tarefas completas nem os gates de release.

Provedores configuráveis: Codex e Claude Code. Inferências reais nesta execução: zero. Benchmark Kimi: não executado.

Veja [resultados](../audit/validation.json), [matriz completa com 400 subtarefas e 160 cenários](../audit/execution-status.json), [guia operacional](../docs/EXECUTION.md) e [pacotes verificados](../audit/distribution.json).

| Tarefa | Estado | Implementação / pendência |
|---|---|---|
| KS-001 | IMPLEMENTACAO_PARCIAL | Inventário e baseline de 368 testes com JUnit/cobertura; bundles comparados sem execução. **Falta:** Revisão manual de toda a proveniência externa ainda não certificada. |
| KS-002 | IMPLEMENTACAO_PARCIAL | Regressões dos defeitos centrais registradas antes dos patches; falhas intermediárias preservadas. **Falta:** Nem todos os 160 cenários propostos foram implementados; primeiro teste de corrida de selo teve argumento CLI corrigido. |
| KS-003 | IMPLEMENTACAO_PARCIAL | Envelopes 0.3, PlanPatch e contratos versionados; migração de snapshots com backup e sem inventar recibos. **Falta:** Todos os envelopes de execução e conversão integral das referências legadas ainda incompletos. |
| KS-004 | IMPLEMENTACAO_PARCIAL | Nove plugins inventariados; pacote kdr-x separado; matriz diferencia capacidade local e integração não comprovada. **Falta:** Direitos de redistribuição dos plugins externos não estabelecidos; substituições independentes pendentes. |
| KS-005 | IMPLEMENTACAO_PARCIAL | Doctor offline/plugin/live, prova de storage e consulta de autenticação Claude Code/Codex. **Falta:** Round-trip real do host e inferência live não executados. |
| KS-006 | IMPLEMENTACAO_PARCIAL | Protocolo versionado com trilhas, desenho pareado, margens e tratamento de falhas. **Falta:** Baseline Kimi identificado, orçamento total e conjunto privado independente ainda ausentes. |
| KS-007 | IMPLEMENTACAO_PARCIAL | Loader tipado, recibos e histórico; invalidação seletiva explícita, replay do corpus preservado e índice sob demanda. **Falta:** Atualização intencional do corpus exige novo run; aceitação formal vinculada ao SHA de PR ainda ausente. |
| KS-008 | IMPLEMENTACAO_PARCIAL | Identidade, bytes, hash, tamanho, parsing e referências observados pelo kernel; testes declarados pelo agente são rejeitados. **Falta:** Staging validado para handlers confiáveis; schemas de todos os formatos e sandbox de código hostil pendentes. |
| KS-009 | IMPLEMENTACAO_PARCIAL | IDs UUID, componentes portáveis, diretório exclusivo e bloqueio de links/travessias. **Falta:** Prova de mil criações reais concorrentes ainda não executada; teste atual gera mil IDs. |
| KS-010 | IMPLEMENTACAO_PARCIAL | Plano persistido e hash/revisão vinculados ao executor; fachadas enviam pedidos ao kernel. **Falta:** Planner council live e conflitos de importação durante execução precisam de aceitação ampliada. |
| KS-011 | IMPLEMENTACAO_PARCIAL | Política comum e deliverable separado do status de tasks em runner, run/resume, status JSON e pedidos do kernel. **Falta:** Aceitação do host real e conclusão semântica independente continuam pendentes. |
| KS-012 | IMPLEMENTACAO_PARCIAL | Bytes, gates próprios da selagem, revisão imutável e checkpoint publicados por transação recuperável; revogação persistida. **Falta:** Lineage de edição manual do relatório até uma nova revisão do plano e ensaios de perda de energia ainda pendentes. |
| KS-013 | IMPLEMENTACAO_PARCIAL | IDs opacos e mapa de IDs legados; parser aceita espaços/Unicode; citações malformadas bloqueadas. **Falta:** Migrador completo dos relatórios legados e referências de todas as integrações pendente. |
| KS-014 | IMPLEMENTACAO_PARCIAL | Trechos por sentença com offsets exatos; gate confere texto contra snapshot e blobs. **Falta:** Localização completa em tabelas, páginas e extrações multimodais ainda não validada. |
| KS-015 | IMPLEMENTACAO_PARCIAL | Cobertura lexical separada de suficiência; lacunas críticas não desaparecem por consultas concluídas. **Falta:** Grafo completo requisito/pergunta/claim e rubricas independentes não implementados. |
| KS-016 | IMPLEMENTACAO_PARCIAL | Counterevidence persistida alimenta edges e standing, com motivos de rejeição. **Falta:** Classificação semântica calibrada e auditoria completa de dupla contagem pendentes. |
| KS-017 | IMPLEMENTACAO_PARCIAL | Transporte com DNS/IP público, peer pinning, redirects revalidados e limites de bytes/tempo. **Falta:** Prova live de DNS rebinding, deadline rígido do resolvedor e política MIME ampliada pendentes. |
| KS-018 | IMPLEMENTACAO_PARCIAL | Objetivo via payload base64/argv e stdin; arquivo global compartilhado removido. **Falta:** Round-trip no host real e matriz de shells não executados. |
| KS-019 | IMPLEMENTACAO_PARCIAL | Fronteiras application/runtime/evidence/integrations extraídas com APIs de compatibilidade. **Falta:** Extração completa de storage/gates/executores ainda em andamento. |
| KS-020 | IMPLEMENTACAO_PARCIAL | SQLite schema 3, CAS, exports recuperáveis, importação legada e backup pré-upgrade com rollback de DDL testado após kill. **Falta:** Importação é arquivo histórico sem retomada de sucesso não comprovado; registry, discos remotos mapeados e perda física de energia pendentes. |
| KS-021 | IMPLEMENTACAO_PARCIAL | Leases, fencing, heartbeats, reconciliação, cancelamento, outbox/inbox, retries limitados e dead letters persistidas. **Falta:** Efeitos externos não têm garantia transacional; integração dos consumidores com todos os hosts ainda pendente. |
| KS-022 | IMPLEMENTACAO_PARCIAL | Staging por tentativa, blobs antes do commit, publicação recuperável, bloqueio de aliases e coleta com retenção/quarentena. **Falta:** Isolamento do sistema operacional para código hostil e durabilidade após perda física de energia não certificados. |
| KS-023 | IMPLEMENTACAO_PARCIAL | Registry executado no planejamento; plano com seis IDs arbitrários, análise de claims e exportação JSON verificado. **Falta:** Backend code continua bloqueado sem sandbox; exportações além de JSON e especialização semântica completa pendentes. |
| KS-024 | IMPLEMENTACAO_PARCIAL | Briefs levam identidade, orçamento e políticas; inferência recebe contexto explícito e ferramentas restringidas. **Falta:** ExecutionSpec tipada completa e enforcement por sandbox do sistema operacional pendentes. |
| KS-025 | IMPLEMENTACAO_PARCIAL | Adaptadores Claude Code e Codex com stdout estruturado, recibos, timeout e seleção explícita. **Falta:** Nenhuma inferência real executada; integração de host e isolamento ainda não certificados. |
| KS-026 | IMPLEMENTACAO_PARCIAL | Quatro workflows reduzidos a fachadas; fala de agente não autoriza selo. **Falta:** Entrega de recibo autenticado dentro do host e round-trip real pendentes. |
| KS-027 | IMPLEMENTACAO_PARCIAL | Execução concorrente real por dependências prontas; teste com barreira de quatro handlers. **Falta:** Semáforos globais por provedor e medição live de throughput pendentes. |
| KS-028 | IMPLEMENTACAO_PARCIAL | Backoff/deadline, timeout/teto de saída de inferência, cancelamento observado por heartbeat e rejeição de resultados tardios. **Falta:** Cancelamento de efeitos arbitrários em threads e teste live da árvore completa de processos pendentes. |
| KS-029 | IMPLEMENTACAO_PARCIAL | Reservas compartilhadas e idempotentes; chamadas limitadas; uso desconhecido não vira custo zero. **Falta:** Limites de tokens/cache/downloads e reconciliação monetária multirrun/provedor incompletos. |
| KS-030 | IMPLEMENTACAO_PARCIAL | Mutação transacional de sessões; corrupção do registry bloqueia; preservação de sessões concorrentes. **Falta:** Importação/recuperação integral do registry, expiração e aceitação de host pendentes. |
| KS-031 | IMPLEMENTACAO_PARCIAL | Restrições de inferência por flags de host e transporte HTTP validado. **Falta:** Sandbox obrigatória do SO, broker de ferramentas, ACL/mounts e provas de escape NÃO implementados. |
| KS-032 | IMPLEMENTACAO_PARCIAL | PlanPatch transacional, histórico imutável, CAS, capacidades/DAG/ownership e invalidação seletiva; leases e recibos vinculados à revisão. **Falta:** Patches exigem fronteira sem tasks em voo; replanejamento automático e reconciliação de todos os tipos de orçamento ainda pendentes. |
| KS-033 | IMPLEMENTACAO_PARCIAL | Mensagens tipadas com escopo/ref, deduplicação, limites, outbox/inbox e recursos ordenados; ajuda aplica aresta via PlanPatch atômico. **Falta:** Comunicação desligada por padrão; ablação de ganho, consumo semântico live e cancelamento após prazo ainda pendentes. |
| KS-034 | IMPLEMENTACAO_PARCIAL | DAG com cinco especialistas e E2E simulado sobre corpus real. **Falta:** Execução com cinco chamadas reais, isolamento e orçamento autorizado pendentes. |
| KS-035 | IMPLEMENTACAO_PARCIAL | FetchResponse tipada com bytes, status, headers, cadeia, duração e erros tipados de transporte. **Falta:** Todos os adapters ainda não convergiram para paginação/retry/cache e envelope único. |
| KS-036 | IMPLEMENTACAO_PARCIAL | OpenAlex tolera primary_location.source nulo. **Falta:** Paginação, expansão bounded e testes live de contratos pendentes. |
| KS-037 | IMPLEMENTACAO_PARCIAL | Crossref conserva data completa quando presente e marca precisão anual sem inventar janeiro. **Falta:** Resolução de versões e metadados completos em todos os provedores pendentes. |
| KS-038 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** GitHub adapter com pin de commit e navegação de código ainda pendente. |
| KS-039 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Ferramentas distintas de busca/fetch/browser e provenance uniforme ainda pendentes. |
| KS-040 | IMPLEMENTACAO_PARCIAL | Snapshots bruto/extraído locais armazenados por SHA-256 e usados na retomada. **Falta:** Snapshots HTTP versionados e exportação portátil de todas as fontes ainda incompletos. |
| KS-041 | IMPLEMENTACAO_PARCIAL | DocumentIR com offsets e blocos; código Markdown preservado; PDF sem texto falha explicitamente. **Falta:** OCR, tabelas/células completas, figuras e validadores de todos os formatos pendentes. |
| KS-042 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Embeddings neurais e reranking medido não implementados; n-gram continua diagnóstico lexical. |
| KS-043 | IMPLEMENTACAO_PARCIAL | Parâmetros ref/source deixaram de ser removidos genericamente; aliases de fontes preservados. **Falta:** Políticas de canonicalização por domínio e near-duplicate auditado pendentes. |
| KS-044 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Planejamento de pesquisa dirigido por grafo de requisitos ainda pendente. |
| KS-045 | IMPLEMENTACAO_PARCIAL | Inventário estático separado dos plugins externos com dependências, endpoints e limitações. **Falta:** Auditoria semântica de cada ferramenta, autorização e contratos live não concluídos. |
| KS-046 | IMPLEMENTACAO_PARCIAL | Auto-instalação latest removida dos scripts de imagem/áudio; capacidades desabilitadas. **Falta:** Build autorizado com dependências pinadas, isolamento e geração real não disponíveis. |
| KS-047 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Tipos financeiros por moeda, unidade, período e frequência ainda pendentes. |
| KS-048 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Plano batch por item/campo e snapshots de tabelas ainda pendente. |
| KS-049 | IMPLEMENTACAO_PARCIAL | Heurística de claims ampliada para português e preservação de escopo composto. **Falta:** Decomposição semântica PT/EN calibrada e anotada independentemente pendente. |
| KS-050 | IMPLEMENTACAO_PARCIAL | Negação oposta derruba overlap; documentação retira garantia semântica. **Falta:** Modelo NLI/LLM calibrado, corpus independente e ablação ainda não implementados. |
| KS-051 | IMPLEMENTACAO_PARCIAL | Divergências numéricas distinguem escopos temporais em casos básicos. **Falta:** Unidades, denominadores, arredondamento, moeda e recálculos tipados completos pendentes. |
| KS-052 | IMPLEMENTACAO_PARCIAL | Escopo temporal compara datas do evento no trecho; data editorial não substitui evento. **Falta:** Event time completo, versões e validade temporal por domínio pendentes. |
| KS-053 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Políticas de qualidade específicas por domínio e validação independente pendentes. |
| KS-054 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Novo grafo de independência por entidade/cadeia causal ainda pendente; heurística anterior permanece. |
| KS-055 | IMPLEMENTACAO_PARCIAL | Busca de contraevidência real no corpus e especialista configurável. **Falta:** Estratégia adversarial por risco, orçamento por lacuna e validação independente pendentes. |
| KS-056 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Calibração de confiança com conjuntos independentes não realizada. |
| KS-057 | IMPLEMENTACAO_PARCIAL | Detecção de afirmações qualitativas não registradas e bloqueio de texto vazio/citação malformada. **Falta:** Cobertura semântica de toda sentença, negações complexas e causalidade não certificada. |
| KS-058 | IMPLEMENTACAO_PARCIAL | Revalidação invalida selo e hashes denunciam mudança de evidência. **Falta:** Grafo completo de lineage e propagação incremental de retratação não implementados. |
| KS-059 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Outline rastreável a requisitos e EvidencePacks mínimos ainda pendentes. |
| KS-060 | IMPLEMENTACAO_PARCIAL | Writer e reviewer são tarefas distintas e chamam o adaptador de modelos selecionado. **Falta:** Provas live, fixer separado com laços limitados e ablação de qualidade pendentes. |
| KS-061 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** ReportIR validada e montagem mecânica multi-formato ainda pendentes. |
| KS-062 | IMPLEMENTACAO_PARCIAL | Certificado de bytes, plano, grafo e política; verify-delivery funciona sem modelo/rede. **Falta:** Bundle portátil autocontido com todos os blobs e revisões, assinatura e compatibilidade pendentes. |
| KS-063 | IMPLEMENTACAO_PARCIAL | Reprodução de cálculo resolve hashes para conteúdo real; hash sozinho não é input. **Falta:** Execução isolada de scripts, unidades e integração de todos os ledgers pendentes. |
| KS-064 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Exportações de documentos/mídia com abertura real por formato ainda pendentes. |
| KS-065 | IMPLEMENTACAO_PARCIAL | Contexto explícito com fontes, spans, claims, pareceres e limite de bytes. **Falta:** Packs mínimos por relevância, tokenização, compactação/expansão auditável e cache pendentes. |
| KS-066 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Seleção medida de arquitetura e número de agentes depende de avaliações ainda ausentes. |
| KS-067 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Replanejamento automático seguro por lacunas e conflitos ainda pendente. |
| KS-068 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Parada por ganho marginal e risco residual calibrado ainda pendente. |
| KS-069 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Memória governada com proteção de datasets e proveniência ainda pendente. |
| KS-070 | PENDENTE | Sem implementação nova certificada nesta execução. **Falta:** Pesquisa incremental de monitoramento com orçamento e aprovação de mudanças ainda pendente. |
| KS-071 | IMPLEMENTACAO_PARCIAL | Hard negatives de regressão para negação, citações, números e identidade. **Falta:** Dataset privado e anotadores independentes não disponíveis; fixtures do autor não contam como held-out. |
| KS-072 | IMPLEMENTACAO_PARCIAL | Provas comportamentais de CAS, concorrência, fencing, rollback por kill, HTTP e selo. **Falta:** Property testing amplo, mutation testing e matriz de ataques do SO ainda não executados. |
| KS-073 | IMPLEMENTACAO_PARCIAL | Wheel instalado fora do checkout; diagnóstico, pesquisa, retomada, selo e consumidor exercitados. **Falta:** Host Claude/Kimi real e sistemas operacionais adicionais não testados. |
| KS-074 | BLOQUEADO_EXTERNO | Sem implementação nova certificada nesta execução. **Falta:** Benchmark contra single-agent e produto Kimi bloqueado por orçamento, acesso identificado e desenho independente. |
| KS-075 | BLOQUEADO_EXTERNO | Sem implementação nova certificada nesta execução. **Falta:** Não há resultados pareados nem revisores independentes para análise estatística e revisão cega. |
| KS-076 | CONDICIONAL_NAO_INICIADO | Sem implementação nova certificada nesta execução. **Falta:** Otimização/treino condicionado a ganhos comprovados; não iniciado sem a evidência exigida. |
| KS-077 | IMPLEMENTACAO_PARCIAL | Eventos SQLite ordenados e recibos de subprocesso/uso, com custo desconhecido explícito. **Falta:** Replay determinístico completo e métricas de spans/trace distribuído pendentes. |
| KS-078 | IMPLEMENTACAO_PARCIAL | Lock de dependências com hashes; builds locais comparados e wheel instalado sem editable. **Falta:** SBOM padronizado, auditoria de dependências, typecheck obrigatório, SHAs de actions, assinatura e publicação pendentes. |
| KS-079 | IMPLEMENTACAO_PARCIAL | README corrigido, histórico preservado, matriz por tarefa e resultados gerados dos JUnits. **Falta:** Proteção da branch consultada em audit/governance-observation.json; rulesets completos e recuperação em todas as plataformas ainda pendentes. |
| KS-080 | CONDICIONAL_NAO_INICIADO | Sem implementação nova certificada nesta execução. **Falta:** Múltiplos hosts condicionados à necessidade medida; nenhuma escala adicional habilitada. |
