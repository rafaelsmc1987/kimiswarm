# Plano cirúrgico — KimiSwarm
## Núcleo confiável → swarm live → superioridade medida

**Repositório:** `rafaelsmc1987/kimiswarm`  
**Baseline:** `main` / `2e2851d820cbed7060064a6584e7eb7f26b25885`  
**Commit observado:** 20/08/2026 08:45:59 UTC  
**Auditoria:** 2026-09-11  
**Estado deste documento:** plano proposto, não implementado.

**80 tarefas · 400 subtarefas · 160 cenários de aceite propostos.**
Prioridades: 20 P0, 52 P1, 7 P2 e 1 P3. Esses números descrevem o backlog; não medem prontidão.

## 1. Diagnóstico e decisão de arquitetura

O núcleo determinístico deve continuar sendo um ativo. Há schemas, DAG, persistência, corpus, verificações, hooks, artefatos e uma suíte de CI real. Entretanto, o scheduler Python é sequencial, o executor principal reconhece quatro IDs e a camada JavaScript delega parte do controle a respostas de agentes. A arquitetura-alvo mantém o núcleo, retira decisões de controle das respostas probabilísticas e conecta especialistas reais por contratos auditáveis. Ver `AUDITORIA_EVIDENCIAS.md`, achados F-01 a F-18, com links fixados no commit.

Não recomendo uma reescrita, microserviços por antecipação, nem 100 agentes como objetivo isolado. Recomendo um monólito modular/sidecar com portas claras, um store transacional e workers isolados. A primeira meta competitiva deve ser pesquisa com rastreabilidade de cada afirmação, recuperação confiável, custo controlado e evidência contra o próprio resultado; depois, ampliar formatos, código, mídia e escala.

### O que foi e não foi demonstrado

O CI histórico de 20/08/2026 aprovou 368 testes em 41,95 s no SHA auditado. O README ainda menciona 234, e o checklist 81/81 pertence a outro ciclo. O registro SW marca 00–03 concluídos e 04–18 pendentes. Os testes de workflow inspecionados verificam estrutura e compilação, não o harness real. **Nesta sessão não foram executados a suíte do repositório, provedores live, testes de carga ou benchmark contra o Kimi.**

A auditoria leu integral ou parcialmente os arquivos listados em `COBERTURA_AUDITORIA.json`. Não equivale a leitura linha a linha de todo o repositório, dos bundles e de todo o histórico. KS-001 exige completar esse inventário e reproduzir a baseline antes dos patches. Nenhum arquivo remoto foi modificado.

## 2. Como executar este backlog

Cada cartão contém prioridade, dependências, papel responsável sugerido, arquivos existentes, arquivos novos propostos, cinco subtarefas concretas e dois cenários de aceite. Os nomes `test_ks_*` são sugestões de implementação; não existem por terem sido escritos neste plano. Os dois cenários por tarefa podem exigir vários casos parametrizados e não substituem toda a cobertura necessária.

A ordem numérica organiza a leitura; **a execução segue o DAG de dependências** em `BACKLOG_KIMISWARM.json`. Por exemplo, KS-025 depende do sandbox KS-031, embora o segundo venha depois no documento. Uma tarefa P0 bloqueia a capacidade afetada; componentes opcionais sem autorização devem ser desativados explicitamente, nunca contados como funcionando.

Para cada PR: implementar primeiro as regressões aplicáveis; alterar o mínimo de superfície; anexar logs ao SHA; submeter revisão independente; demonstrar rollback. Não concluir por existir uma classe, uma string no prompt, um JSON com `passed=true` ou uma lista de testes declarados. Só fazer merge após evidência executada e gates passarem sem relaxamento de critérios.

### Definição de prioridades

**P0:** incorreção, falsa aprovação, segurança, perda de estado ou proveniência que bloqueia a capacidade afetada.  
**P1:** necessário para o produto alvo funcionar de ponta a ponta e atingir qualidade competitiva.  
**P2:** otimização/expansão após estabilização do caminho principal.  
**P3:** escala distribuída condicionada a necessidade medida.

## 3. Arquitetura-alvo

```text
CLI / plugin / interface
  → ApplicationService: única autoridade de plano e estado
  → contrato + DAG versionado + store transacional
  → scheduler por prontidão + leases + orçamento
  → backend(s) suportado(s) → workers isolados → ToolBroker
  → snapshots imutáveis → evidência exata → claims/refutação
  → ReportIR → montagem → gates sobre os mesmos bytes
  → certificado verificável → entrega
```

Uma resposta de modelo pode propor uma claim, plano ou revisão; não concede permissões, não comprova gasto/exit code e não confirma seu próprio commit. O kernel consulta o registry e valida artefatos reais. Manter uma só autoridade; JSON/JSONL são exportações legíveis e checkpoints, não bancos concorrentes.

Para a primeira implantação single-host, proponho SQLite WAL com transações curtas, um escritor por vez e durabilidade definida. Não usar WAL em filesystem de rede. Verificar a versão SQLite vinculada ao Python e a correção WAL-reset; a documentação registra correção em 3.51.3 e backports específicos. O PR deve validar a versão instalada, não apenas o pacote Python. Fonte: EXT-06.

O workflow Claude Code é uma fachada limitada por seu host: a documentação consultada admite até 16 agentes simultâneos. Não inserir `require`, import dinâmico ou acesso direto a filesystem no corpo do workflow proibido pelo contrato. Mais concorrência exige backend próprio compatível, não uma configuração fictícia. Fontes: EXT-01 a EXT-03.

### Estrutura proposta, migrada por etapas

```text
src/kdrx/
  schemas/                 # contratos versionados, compatibilidade
  application/             # serviços de caso de uso
  runtime/                 # store, scheduler, leases, orçamento, backends
  integrations/            # HTTP, busca, browser, SDKs e formatos
  evidence/                # DocumentIR, spans, claims, relações
  synthesis/               # ReportIR, edição e montagem
  evaluation/              # runners, conjuntos e estatística
  observability/           # traces, uso, replay e privacidade
  cli.py                   # fachada; migrar sem quebrar comandos
plugins/kdr-x/             # adaptação ao host, não estado paralelo
```

Esses diretórios são alvos propostos, não estruturas existentes no SHA auditado. Os módulos atuais permanecem como fachadas de compatibilidade durante a migração. Não mover todos os arquivos num PR gigante: extrair por serviço, preservar testes e reduzir ciclos de import.

## 4. Gates de liberação

### G0 — Baseline auditável

Inventário residual concluído, suíte reproduzida, capacidades e indisponibilidades registradas. Testes de regressão representam os defeitos, não apenas a estrutura.

**Tarefas:** KS-001, KS-002, KS-003, KS-004, KS-005, KS-006

### G1 — Núcleo confiável

Retomada parcial, identidade, artefatos reais, plano canônico, citações e selo sem falsa aprovação. Toda pendência crítica está explícita.

**Tarefas:** KS-007, KS-008, KS-009, KS-010, KS-011, KS-012, KS-013, KS-014, KS-015, KS-016, KS-017, KS-018

### G2 — Swarm live unificado e seguro

Execução real com pelo menos cinco especialistas, concorrência medida, isolamento, budget, cancelamento, commits duráveis e retomada após falhas.

**Tarefas:** KS-019, KS-020, KS-021, KS-022, KS-023, KS-024, KS-025, KS-026, KS-027, KS-028, KS-029, KS-030, KS-031, KS-032, KS-033, KS-034

### G3 — Pesquisa e relatório verificáveis

Fontes reais, spans exatos, provas semânticas e numéricas, refutação integrada e cada afirmação material ligada à sua evidência. Capacidades externas só contam quando autorizadas e testadas.

**Tarefas:** KS-035, KS-036, KS-037, KS-038, KS-039, KS-040, KS-041, KS-042, KS-043, KS-044, KS-045, KS-046, KS-047, KS-048, KS-049, KS-050, KS-051, KS-052, KS-053, KS-054, KS-055, KS-056, KS-057, KS-058, KS-059, KS-060, KS-061, KS-062, KS-063, KS-064

### G4 — Release operacional

Instalação limpa na matriz suportada, isolamento/chaos regressions, observabilidade e rollback. CI não declara capacidades não verificadas.

**Tarefas:** KS-072, KS-073, KS-077, KS-078, KS-079

### G5 — Superioridade demonstrada no escopo

Protocolo pré-registrado, held-out não contaminado, comparação real e pareada, intervalos e custo/latência publicados. Ausência de resultado positivo não pode ser escondida.

**Tarefas:** KS-065, KS-066, KS-067, KS-068, KS-069, KS-071, KS-072, KS-073, KS-074, KS-075, KS-076


Gates exigem também o fechamento transitivo das dependências. G5 não depende de capacidade opcional não usada no experimento; uma alegação ampla exige todos os domínios correspondentes. KS-070 (monitoramento contínuo) e KS-080 (escala) só são obrigatórios quando fizerem parte da oferta/alegação.

**“100% funcionando” deve significar:** 100% dos critérios declarados para a versão e matriz de suporte passam; falhas, cancelamentos e limites têm comportamento definido. Não significa ausência garantida de falhas para toda entrada futura. “Zero falhas críticas” é um resultado da suíte, não uma probabilidade universal zero.

**Entrega ≠ selo:** o selo atesta integridade e identidade dos bytes; a aptidão para entrega depende de critérios adicionais. Nem hash nem consenso de agentes provam, sozinhos, a verdade de uma afirmação. 

**Exactly-once externo não é presumido:** para chamadas que podem ter produzido efeito antes de timeout, usar chave de idempotência quando disponível e reconciliação quando não. Uma tentativa com resultado desconhecido não deve ser repetida como se nada tivesse acontecido.

## 5. Ordem de execução verificada

A sequência abaixo é uma ordenação topológica válida; tarefas independentes podem ser feitas em paralelo respeitando os mesmos arquivos/contratos. Ela não é estimativa de tempo.


KS-001 → KS-002 → KS-003 → KS-004 → KS-006 → KS-017 → KS-007 → KS-008 → KS-009 → KS-011 → KS-013 → KS-005 → KS-010 → KS-018 → KS-012 → KS-014 → KS-019 → KS-015 → KS-020 → KS-016 → KS-021 → KS-022 → KS-023 → KS-024 → KS-027 → KS-030 → KS-031 → KS-032 → KS-033 → KS-025 → KS-026 → KS-028 → KS-029 → KS-072 → KS-034 → KS-035 → KS-036 → KS-037 → KS-038 → KS-039 → KS-040 → KS-045 → KS-041 → KS-043 → KS-077 → KS-046 → KS-047 → KS-073 → KS-042 → KS-048 → KS-078 → KS-044 → KS-079 → KS-049 → KS-050 → KS-052 → KS-051 → KS-053 → KS-063 → KS-054 → KS-055 → KS-056 → KS-057 → KS-059 → KS-065 → KS-058 → KS-071 → KS-060 → KS-066 → KS-069 → KS-061 → KS-067 → KS-062 → KS-068 → KS-064 → KS-070 → KS-074 → KS-075 → KS-076 → KS-080

## 6. Índice das tarefas


### A — Correção e contratos

- **KS-001 [P0]** Congelar baseline verificável e completar inventário residual

- **KS-002 [P0]** Transformar os achados em regressões vermelhas antes dos patches

- **KS-003 [P0]** Versionar contratos e reforçar validação de identidade

- **KS-004 [P0]** Separar produto MIT, plugins externos e capacidades indisponíveis

- **KS-005 [P0]** Tornar doctor diagnóstico de capacidade real

- **KS-006 [P0]** Registrar benchmark e regra de vitória antes de otimizar

- **KS-007 [P0]** Corrigir reidratação na retomada parcial

- **KS-008 [P0]** Validar resultados e arquivos fora da palavra do agente

- **KS-009 [P0]** Eliminar colisões de runs e escapes pelo identificador

- **KS-010 [P0]** Usar um único plano canônico em plan/run/deep-research

- **KS-011 [P0]** Unificar semântica de verify, seal e pronto para entrega

- **KS-012 [P0]** Selar exatamente os bytes verificados e revogar selos obsoletos

- **KS-013 [P0]** Corrigir IDs de fontes e parsing de citações

- **KS-014 [P0]** Ligar cada claim ao trecho que realmente a contém

- **KS-015 [P0]** Não confundir cobertura lexical com cobertura de pesquisa

- **KS-016 [P0]** Conectar counterevidence persistida ao standing

- **KS-017 [P0]** Fechar SSRF e limites de leitura antes de liberar rede

- **KS-018 [P0]** Eliminar shell frágil e corrida no arquivo de objetivo


### B — Runtime durável e agentes

- **KS-019 [P1]** Extrair fronteiras internas sem reescrita total

- **KS-020 [P1]** Substituir read-modify-write de JSON por estado transacional

- **KS-021 [P1]** Implementar leases, fencing e eventos sem dupla conclusão

- **KS-022 [P1]** Criar staging de artefatos e commit recuperável

- **KS-023 [P1]** Despachar por capacidade e papel, não por quatro task IDs

- **KS-024 [P1]** Materializar especialização e privilégio mínimo por tarefa

- **KS-025 [P1]** Implementar um backend live real e portável

- **KS-026 [P1]** Reduzir workflows a fachadas do kernel

- **KS-027 [P1]** Executar DAG com concorrência real e prontidão por dependência

- **KS-028 [P1]** Aplicar retries, deadline e cancelamento no efeito real

- **KS-029 [P1]** Controlar orçamento compartilhado antes de gastar

- **KS-030 [P1]** Fortalecer hooks nativos e registry de sessões

- **KS-031 [P0]** Isolar workers e intermediar ferramentas com políticas

- **KS-032 [P1]** Revisar plano sem invalidar trabalho corretamente concluído

- **KS-033 [P1]** Coordenar agentes com mensagens tipadas e orçamento

- **KS-034 [P1]** Fechar o primeiro E2E live realmente unificado


### C — Pesquisa e capacidades reais

- **KS-035 [P1]** Padronizar transportes e resultados de adapters

- **KS-036 [P1]** Robustecer OpenAlex e cobertura de literatura

- **KS-037 [P1]** Preservar datas e versões em DOI, Crossref e arXiv

- **KS-038 [P1]** Pesquisar código com identidade de commit e conteúdo

- **KS-039 [P1]** Adicionar busca web e navegador como capacidades distintas

- **KS-040 [P1]** Criar snapshots imutáveis com proveniência de extração

- **KS-041 [P1]** Extrair documentos preservando tabelas, código e coordenadas

- **KS-042 [P1]** Adicionar retrieval semântico mensurável sem remover BM25

- **KS-043 [P1]** Evitar deduplicação destrutiva e aliases semânticos de URL

- **KS-044 [P1]** Planejar consultas por lacuna, idioma e tempo

- **KS-045 [P0]** Auditar e normalizar os oito plugins externos ao kdr-x

- **KS-046 [P1]** Tornar geração de imagem e áudio independente de instalação mutável

- **KS-047 [P1]** Validar dados financeiros, econômicos e acadêmicos por contrato

- **KS-048 [P1]** Implementar pesquisa em lote por itens e campos


### D — Evidência e raciocínio verificável

- **KS-049 [P1]** Decompor claims semanticamente em português e inglês

- **KS-050 [P1]** Verificar entailment sem usar vocabulário como prova

- **KS-051 [P1]** Verificar números, unidades e comparações reproduzivelmente

- **KS-052 [P1]** Separar tempo do fato, publicação e observação

- **KS-053 [P1]** Avaliar qualidade da fonte segundo domínio e tipo de alegação

- **KS-054 [P1]** Calcular independência de evidência, não contagem de URLs

- **KS-055 [P1]** Pesquisar contraevidência dirigida por risco

- **KS-056 [P1]** Calibrar confiança e distinguir desconhecido de falso

- **KS-057 [P1]** Cobrir todas as afirmações materiais do texto final

- **KS-058 [P1]** Propagar alterações de evidência até as entregas


### E — Relatórios, cálculos e artefatos

- **KS-059 [P1]** Planejar relatório por requisitos e evidência

- **KS-060 [P1]** Executar writers, reviewers e fixers reais

- **KS-061 [P1]** Montar relatório mecanicamente a partir de IR validada

- **KS-062 [P1]** Adicionar certificado de entrega verificável por consumidor

- **KS-063 [P1]** Corrigir reprodução de cálculos por conteúdo real

- **KS-064 [P1]** Entregar documentos e mídia com verificação de abertura


### F — Inteligência adaptativa

- **KS-065 [P2]** Construir ContextPacks mínimos e compactação auditável

- **KS-066 [P2]** Escolher arquitetura e número de agentes por tarefa

- **KS-067 [P2]** Replanejar a partir de lacunas e conflitos reais

- **KS-068 [P2]** Parar por ganho marginal e risco residual

- **KS-069 [P2]** Adicionar memória governada sem contaminar avaliações

- **KS-070 [P2]** Transformar monitoramento local em pesquisa incremental controlada


### G — Prova comparativa

- **KS-071 [P1]** Criar datasets adversariais separados do código de detecção

- **KS-072 [P1]** Testar propriedades, falhas e invariantes de segurança

- **KS-073 [P1]** Executar testes reais do host em instalações limpas

- **KS-074 [P1]** Comparar contra single-agent e Kimi com condições documentadas

- **KS-075 [P1]** Demonstrar ganho com estatística e revisão cega

- **KS-076 [P2]** Otimizar e eventualmente treinar o coordenador com dados confiáveis


### H — Operação, release e escala

- **KS-077 [P1]** Medir execução, custo, erros e proveniência em uma trilha

- **KS-078 [P1]** Publicar wheel/plugin reproduzíveis com supply chain verificável

- **KS-079 [P1]** Gerar documentação de estado real e governança consistente

- **KS-080 [P3]** Escalar para múltiplos hosts apenas após demonstrar necessidade


## 7. Tarefas e subtarefas


## A — Correção e contratos


### KS-001 — Congelar baseline verificável e completar inventário residual

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** sem dependências

**Correspondência com roadmap anterior:** SW-17

**Arquivos atuais afetados:** `README.md`, `pyproject.toml`, `tests/`, `.github/`, `evidence-manifest/`

**Novos caminhos propostos:** `audit/baseline.json`, `scripts/audit_inventory.py`

**Motivação:** A auditoria está fixada no SHA indicado. O CI histórico consultado aprovou 368 testes; isso não equivale a uma nova execução local ou live.

**Achados relacionados:** F-16, F-17

#### Subtarefas

- [ ] **KS-001.1** Gerar inventário com git ls-files -z, tamanho, SHA-256 e classificação produto/teste/documentação/terceiro/binário; incluir arquivos ocultos e marcar explicitamente o que exige inspeção manual.

- [ ] **KS-001.2** Instalar o checkout exato em ambiente descartável; capturar versões Python, Node, Claude Code, sistema, dependências e origem do import kdrx.

- [ ] **KS-001.3** Executar a suíte sem suprimir skips, coletar JUnit e cobertura por linha/branch; comparar com o job 96368225974, sem tratar resultados antigos como execução nova.

- [ ] **KS-001.4** Percorrer scripts de release, workflows CI, hooks restantes e cada bundle.zip sem executá-lo; registrar membros, licenças e diferenças entre bundle e fonte expandida.

- [ ] **KS-001.5** Publicar baseline.json com ferramentas que realmente funcionaram, falhas, custos e caminhos não auditados; não produzir porcentagem arbitrária de prontidão.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-001-1** (`test_ks_001_1`): O mesmo checkout gera inventário idêntico; arquivos não classificados impedem declarar inventário completo.

- **AT-001-2** (`test_ks_001_2`): Relatório diferencia testes passados, falhos, ignorados, apenas inspecionados e integrações indisponíveis.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-002 — Transformar os achados em regressões vermelhas antes dos patches

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-001

**Correspondência com roadmap anterior:** SW-00, SW-03, SW-06, SW-11

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/scheduler.py`, `src/kdrx/state.py`, `src/kdrx/reporting.py`

**Novos caminhos propostos:** `tests/regression/test_audit_20260911.py`

**Motivação:** Os problemas de integração escapam de testes que verificam apenas nomes, schemas ou execuções já concluídas.

**Achados relacionados:** F-02, F-16

#### Subtarefas

- [ ] **KS-002.1** Adicionar caso de retomada com T-RETRIEVE concluída e T-VERIFY pendente, usando outro objeto RunState e outro processo.

- [ ] **KS-002.2** Adicionar retorno de agente com task_id errado, lista de outputs declarados mas arquivos inexistentes e tentativa de escrita fora da área da tarefa.

- [ ] **KS-002.3** Adicionar duas criações no mesmo segundo, run_id com traversal e citações cujos IDs incluem subdiretório, espaço, Unicode ou URL.

- [ ] **KS-002.4** Adicionar negação sem alteração do vocabulário principal, afirmação inventada sem número e relatório vazio com corpus válido.

- [ ] **KS-002.5** Adicionar mutação controlada entre a leitura verificada do relatório e a leitura do selo; salvar a falha esperada sem transformar xfail permanente em aprovação.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-002-1** (`test_ks_002_1`): Os casos reproduzem comportamentos do baseline ou são reclassificados com evidência; não presumir que toda hipótese falhará.

- **AT-002-2** (`test_ks_002_2`): Após cada correção correspondente, o teste passa sem remover as asserções ou reduzir thresholds.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-003 — Versionar contratos e reforçar validação de identidade

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-001

**Correspondência com roadmap anterior:** SW-02, SW-04

**Arquivos atuais afetados:** `src/kdrx/schemas/plan.py`, `src/kdrx/schemas/request.py`, `src/kdrx/schemas/corpus.py`, `src/kdrx/schemas/artifact.py`

**Novos caminhos propostos:** `src/kdrx/contracts/versioning.py`, `tests/contracts/test_versions.py`

**Motivação:** TaskSpec possui muitos campos úteis, mas AgentBrief não transporta orçamento/deadline e não há migração explícita comum para todos os artefatos.

**Achados relacionados:** F-18

#### Subtarefas

- [ ] **KS-003.1** Introduzir schema_version e versão de plano em envelopes de run, task, attempt, result, source, evidence e delivery; manter leitor compatível com v0.2.0.

- [ ] **KS-003.2** Validar identidade run_id/plan_id/task_id/attempt_id e limites não negativos no próprio schema; distinguir orçamento ilimitado de orçamento zero.

- [ ] **KS-003.3** Adicionar referências de artefato tipadas, hash, MIME, tamanho, versão e produtor; separar caminhos físicos de identificadores lógicos.

- [ ] **KS-003.4** Gerar JSON Schemas a partir do modelo canônico e comparar com os schemas usados nos workflows; evitar copiar listas de campos à mão.

- [ ] **KS-003.5** Criar migração pura v0.2.0 para a nova versão, com cópia de segurança e sem preencher como verificado aquilo que o formato antigo não registrava.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-003-1** (`test_ks_003_1`): Round-trip preserva todos os campos e rejeita resultado de outro run/attempt.

- **AT-003-2** (`test_ks_003_2`): Artefato de versão desconhecida falha com erro de compatibilidade, não com valores padrão silenciosos.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-004 — Separar produto MIT, plugins externos e capacidades indisponíveis

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-001

**Correspondência com roadmap anterior:** SW-01, SW-17

**Arquivos atuais afetados:** `LICENSE`, `docs/LICENSE_MATRIX.md`, `plugins/`, `plugins/scholar/kimi.plugin.json`

**Novos caminhos propostos:** `plugins/CAPABILITY_MATRIX.json`, `docs/THIRD_PARTY_RELEASE_POLICY.md`

**Motivação:** Existem nove diretórios de plugins; scholar declara UNLICENSED e a licença raiz limita o escopo original a plugins/kdr-x.

**Achados relacionados:** F-15

#### Subtarefas

- [ ] **KS-004.1** Inventariar separadamente kdr-x, github, scholar, sec_edgar, imf, world_bank_open_data, yahoo_finance, image_generation e audio_generation.

- [ ] **KS-004.2** Para cada plugin registrar origem, licença declarada, autorização/documentação disponível, dependências, endpoint, autenticação, dados enviados e suporte de runtime.

- [ ] **KS-004.3** Impedir que o pacote comercial inclua componentes com direitos de redistribuição não estabelecidos; não assumir que a licença MIT da raiz os relicencia.

- [ ] **KS-004.4** Classificar capacidades como implemented-offline, implemented-live-tested, external-unverified, disabled ou planned, com evidência por versão.

- [ ] **KS-004.5** Substituir componentes de origem incompatível por implementações independentes ou integrações oficialmente autorizadas; conservar avisos e proveniência.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-004-1** (`test_ks_004_1`): Uma release com componente de licença não resolvida é bloqueada ou exclui explicitamente esse componente.

- **AT-004-2** (`test_ks_004_2`): Capability matrix nunca declara geração de imagem ou busca acadêmica operacional apenas porque existe uma pasta.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-005 — Tornar doctor diagnóstico de capacidade real

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-003, KS-004

**Correspondência com roadmap anterior:** SW-01

**Arquivos atuais afetados:** `src/kdrx/cli.py`, `pyproject.toml`, `plugins/kdr-x/.claude-plugin/plugin.json`

**Novos caminhos propostos:** `tests/integration/test_doctor_capabilities.py`

**Motivação:** O doctor atual testa imports, manifesto e um executor fictício; raiz de plugin ausente vira WARN.

**Achados relacionados:** F-13

#### Subtarefas

- [ ] **KS-005.1** Separar doctor --profile offline, plugin e live; cada perfil possui requisitos próprios e resultado machine-readable.

- [ ] **KS-005.2** No perfil plugin exigir manifesto, descoberta de agentes, kdr no PATH, versão suportada do host e round-trip real de hook em ambiente limpo.

- [ ] **KS-005.3** No perfil offline validar extratores instalados, permissões da pasta, banco, espaço em disco e geração/leitura de artefato temporário.

- [ ] **KS-005.4** No perfil live fazer apenas probes explicitamente habilitados, com limite de custo, credenciais redigidas e classificação de erros de autenticação/rede/quota.

- [ ] **KS-005.5** Exibir funcionalidades indisponíveis e a ação corretiva exata; proibir status saudável global quando um requisito obrigatório foi pulado.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-005-1** (`test_ks_005_1`): Sem raiz do plugin, perfil plugin retorna falha explícita; perfil offline continua utilizável.

- **AT-005-2** (`test_ks_005_2`): Um provedor não autenticado aparece como indisponível, não como busca sem resultados.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-006 — Registrar benchmark e regra de vitória antes de otimizar

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-001

**Correspondência com roadmap anterior:** SW-16

**Arquivos atuais afetados:** `src/kdrx/evals.py`, `auditoria/sota-2026-08-19/ROADMAP_SOTA_SWARM.json`

**Novos caminhos propostos:** `evals/protocol_v1.json`, `evals/baselines/README.md`

**Motivação:** Scorecards internos e detectores seeded não demonstram superioridade ao produto Kimi.

**Achados relacionados:** F-17

#### Subtarefas

- [ ] **KS-006.1** Definir três trilhas distintas: invariantes de engenharia, qualidade de pesquisa e comparação de produto; não misturar notas em um número opaco.

- [ ] **KS-006.2** Congelar baseline single-agent com mesmo modelo/ferramentas, baseline do próprio commit e baseline Kimi Agent Swarm identificado por versão/data.

- [ ] **KS-006.3** Pré-definir orçamento, deadline, fontes permitidas, política de retry, tratamento de timeout e critério de sucesso por tarefa.

- [ ] **KS-006.4** Separar desenvolvimento, seleção de hiperparâmetros e conjunto privado final; registrar hashes e responsáveis pelo acesso.

- [ ] **KS-006.5** Definir margem mínima útil, não inferioridade de segurança/factualidade e análise estatística antes de observar os resultados finais.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-006-1** (`test_ks_006_1`): É impossível trocar baseline ou remover tarefas difíceis sem gerar nova versão do protocolo.

- **AT-006-2** (`test_ks_006_2`): Uma nota interna alta sem execução dos concorrentes não autoriza o rótulo SOTA.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-007 — Corrigir reidratação na retomada parcial

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-002, KS-003

**Correspondência com roadmap anterior:** SW-06

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/cli.py`, `tests/test_phase4_resume.py`

**Novos caminhos propostos:** `tests/regression/test_partial_resume.py`

**Motivação:** resume_run marca tasks concluídas e instancia _FileResearchExecutor vazio; o próximo _verify depende de self.sources.

**Achados relacionados:** F-02

#### Subtarefas

- [ ] **KS-007.1** Criar loader tipado para sources.jsonl, spans.jsonl, claims.jsonl, standings e relatório, validando integridade antes de reconstruir o executor.

- [ ] **KS-007.2** Associar cada task concluída aos artefatos realmente comprometidos e aos hashes dos seus inputs; não sintetizar sucesso a partir apenas de completed_tasks.

- [ ] **KS-007.3** Invalidar apenas a task cujos artefatos sumiram ou mudaram e seus descendentes; distinguir dano de disco de atualização intencional do corpus.

- [ ] **KS-007.4** Carregar índice FileCorpus quando uma task pendente precisar pesquisar; não confundir fontes reidratadas com índice de busca disponível.

- [ ] **KS-007.5** Adicionar checkpoint após cada fronteira de tarefa e definir retomada concluída como operação idempotente, sem reexecutar pesquisa nem reescrever resultados desnecessariamente.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-007-1** (`test_ks_007_1`): Matar após retrieval e retomar em processo novo conclui sem repetir retrieval nem falhar por fontes vazias.

- **AT-007-2** (`test_ks_007_2`): Artefato concluído adulterado bloqueia retomada ou exige invalidação explícita e registrada.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-008 — Validar resultados e arquivos fora da palavra do agente

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-002, KS-003

**Correspondência com roadmap anterior:** SW-04, SW-05

**Arquivos atuais afetados:** `src/kdrx/scheduler.py`, `src/kdrx/hooks.py`, `src/kdrx/schemas/plan.py`

**Novos caminhos propostos:** `src/kdrx/runtime/result_validator.py`, `tests/regression/test_real_outputs.py`

**Motivação:** _validate_outcome verifica cobertura de listas e contagem de refs, não a existência dos bytes nem identidade completa.

**Achados relacionados:** F-01

#### Subtarefas

- [ ] **KS-008.1** Comparar run/task/attempt/role do resultado com a execução autorizada antes de qualquer transição para sucesso.

- [ ] **KS-008.2** Abrir cada output em staging autorizado, exigir existência, tamanho mínimo quando cabível, MIME e schema esperado; rejeitar symlinks e aliases indevidos.

- [ ] **KS-008.3** Calcular hash dos bytes no broker e registrar produtor; não aceitar hash ou executed_tests fornecido pelo próprio modelo como prova.

- [ ] **KS-008.4** Resolver evidence_refs para objetos persistidos; rejeitar refs inexistentes, extras não autorizados e produtor incompatível.

- [ ] **KS-008.5** Só emitir task_succeeded após validação e commit; devolver erros estruturados para um repair limitado e específico.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-008-1** (`test_ks_008_1`): Agente declara que escreveu arquivo inexistente: task não sucede.

- **AT-008-2** (`test_ks_008_2`): Resultado de task_id ou attempt_id errado é rejeitado mesmo com conteúdo e schema aparentemente válidos.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-009 — Eliminar colisões de runs e escapes pelo identificador

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-002, KS-003

**Correspondência com roadmap anterior:** SW-00, SW-06

**Arquivos atuais afetados:** `src/kdrx/state.py`, `src/kdrx/runner.py`, `src/kdrx/cli.py`

**Novos caminhos propostos:** `tests/regression/test_run_identity.py`

**Motivação:** run_id_from_plan usa segundos; RunState constrói root / run_id sem validar o componente.

**Achados relacionados:** F-05, F-18

#### Subtarefas

- [ ] **KS-009.1** Gerar ID com entropia suficiente e timestamp separado de apresentação; não depender do slug do contrato para unicidade.

- [ ] **KS-009.2** Restringir run_id a um componente opaco de caminho, rejeitando pontos especiais, separadores, absolutos e sintaxes Windows de volume.

- [ ] **KS-009.3** Criar o diretório de run em modo exclusivo; existência anterior exige comando explícito de retomada, nunca sobrescrita pelo scaffold.

- [ ] **KS-009.4** Validar que run_dir, manifest.run_id e root_dir resolvem para o mesmo run autorizado em todos os comandos.

- [ ] **KS-009.5** Testar aliases por case, Unicode e junction/symlink nas plataformas suportadas sem ler conteúdo fora do root.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-009-1** (`test_ks_009_1`): Mil criações concorrentes produzem mil IDs e manifests distintos.

- **AT-009-2** (`test_ks_009_2`): IDs ../../x, caminho absoluto e drive Windows são rejeitados antes de qualquer criação ou leitura.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-010 — Usar um único plano canônico em plan/run/deep-research

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-003, KS-008

**Correspondência com roadmap anterior:** SW-02, SW-05

**Arquivos atuais afetados:** `plugins/kdr-x/workflows/kdr-run.js`, `plugins/kdr-x/workflows/kdr-deep-research.js`, `src/kdrx/runner.py`, `src/kdrx/cli.py`

**Novos caminhos propostos:** `tests/contracts/test_plan_handoff.py`

**Motivação:** kdr-run reduz campos via leitura por LLM; deep-research possui council/síntese próprios e executa waves devolvidas pelo modelo.

**Achados relacionados:** F-03

#### Subtarefas

- [ ] **KS-010.1** Fazer o council produzir ResearchPlan completo, importar via validação canônica e retornar apenas run_id, plan_revision e plan_hash autorizados.

- [ ] **KS-010.2** Eliminar a projeção reduzida de TaskSpec que perde role/tools/skills/budget/retry/acceptance; workers recebem a especificação do kernel.

- [ ] **KS-010.3** Exigir comparação do hash armazenado com o plano efetivamente executado, tanto em run quanto em resume.

- [ ] **KS-010.4** Consolidar as duas implementações de planejamento; workflow standalone e deep-research devem consumir o mesmo plano persistido.

- [ ] **KS-010.5** Rejeitar revisão de plano que altere tarefas já executadas sem procedimento explícito de invalidação; preservar as disposições do council.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-010-1** (`test_ks_010_1`): Todos os campos de TaskSpec chegam ao worker sem alteração na cadeia completa.

- **AT-010-2** (`test_ks_010_2`): Alterar uma wave apenas na resposta do LLM não altera a execução autorizada.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-011 — Unificar semântica de verify, seal e pronto para entrega

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-002, KS-003

**Correspondência com roadmap anterior:** SW-03

**Arquivos atuais afetados:** `src/kdrx/cli.py`, `src/kdrx/runner.py`, `src/kdrx/native_hooks.py`, `src/kdrx/schemas/artifact.py`

**Novos caminhos propostos:** `src/kdrx/delivery/policy.py`, `tests/regression/test_delivery_policy.py`

**Motivação:** cmd_verify informa falha de DAG mas não a inclui em all_pass; cmd_seal inclui DAG e permite críticas não resolvidas com aviso ao Stop.

**Achados relacionados:** F-04

#### Subtarefas

- [ ] **KS-011.1** Definir estados distintos VERIFIED, SEALED e DELIVERABLE; sealed deve significar vínculo criptográfico, não aprovação semântica universal.

- [ ] **KS-011.2** Criar uma política canônica que cheque plano, outputs, fontes, claims, números, segurança e requisitos de entrega, consumida por CLI e hooks.

- [ ] **KS-011.3** Exigir relatório não vazio e detecção de afirmações relevantes sem registro; definir comportamento explícito para resultado inconclusivo permitido.

- [ ] **KS-011.4** Não retornar deliverable=true quando há claim crítica sem resolução obrigatória; quando o contrato permite abstenção, exigir ressalva verificável.

- [ ] **KS-011.5** Remover leitores tolerantes que convertam JSONL corrompido em lista vazia no caminho de entrega; corrupção deve ser diagnóstico bloqueante.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-011-1** (`test_ks_011_1`): verify, seal e Stop concordam sobre elegibilidade e exibem a mesma lista de bloqueios.

- **AT-011-2** (`test_ks_011_2`): Um selo de bytes pode existir para relatório inconclusivo, mas a API nunca o anuncia como entrega aprovada fora da política.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-012 — Selar exatamente os bytes verificados e revogar selos obsoletos

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-008, KS-011

**Correspondência com roadmap anterior:** SW-03, SW-06

**Arquivos atuais afetados:** `src/kdrx/cli.py`, `src/kdrx/runner.py`, `src/kdrx/state.py`

**Novos caminhos propostos:** `tests/regression/test_seal_toctou.py`

**Motivação:** cmd_seal verifica uma leitura e seal_delivery relê o arquivo; não há transação comum que garanta identidade dessas leituras.

**Achados relacionados:** F-04

#### Subtarefas

- [ ] **KS-012.1** Verificar um blob imutável identificado por hash, não um caminho mutável que será relido depois.

- [ ] **KS-012.2** Vincular gate_id, policy_version, plan_hash, graph_revision e report_hash ao mesmo delivery revision.

- [ ] **KS-012.3** Publicar manifest de entrega e eventos em commit atômico; atualizar apenas um ponteiro para a revisão final aprovada.

- [ ] **KS-012.4** Se uma nova validação falhar, manter o selo antigo como histórico mas retirar sua elegibilidade de entrega atual; não deixar sealed=true obsoleto.

- [ ] **KS-012.5** Impedir Write/Edit após publicação; alterações legítimas geram novo blob, nova revisão e nova validação.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-012-1** (`test_ks_012_1`): Trocar o relatório entre verificação e publicação não resulta em selo para bytes não examinados.

- **AT-012-2** (`test_ks_012_2`): Após tampering e nova validação falha, nenhum comando retorna o selo antigo como aprovação atual.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-013 — Corrigir IDs de fontes e parsing de citações

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-002, KS-003

**Correspondência com roadmap anterior:** SW-11, SW-12

**Arquivos atuais afetados:** `src/kdrx/reporting.py`, `src/kdrx/adapters.py`, `src/kdrx/retrieval.py`, `src/kdrx/schemas/corpus.py`

**Novos caminhos propostos:** `tests/regression/test_citation_identifiers.py`

**Motivação:** _CITE_RE aceita alfabeto restrito, mas adapters e FileCorpus produzem IDs com barras, URLs, espaços e caminhos.

**Achados relacionados:** F-06

#### Subtarefas

- [ ] **KS-013.1** Definir SourceId opaco estável, independente da URL ou do caminho de exibição; manter canonical_uri e original_path em campos separados.

- [ ] **KS-013.2** Migrar IDs antigos preservando mapa old_id -> new_id e atualizar spans, edges, claims e referências de forma transacional.

- [ ] **KS-013.3** Trocar parsing frouxo de marcadores por parser de referência do ReportIR; marcador malformado deve ser erro, não desaparecer da contagem.

- [ ] **KS-013.4** Gerar citações somente a partir de refs validadas e resolver bibliografia usando o mesmo registry.

- [ ] **KS-013.5** Adicionar round-trip com URLs com querystring, DOI com barra, nomes Unicode, subdiretórios e nomes contendo espaços.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-013-1** (`test_ks_013_1`): Citar fonte web ou arquivo aninhado produz exatamente uma referência resolvida.

- **AT-013-2** (`test_ks_013_2`): Marcador desconhecido ou malformado impede aprovação, mesmo quando a lista extraída ficaria vazia.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-014 — Ligar cada claim ao trecho que realmente a contém

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-002, KS-003, KS-013

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/corpus.py`, `src/kdrx/schemas/corpus.py`

**Novos caminhos propostos:** `tests/regression/test_claim_exact_span.py`

**Motivação:** _extract_claims usa span_by_source e associa todas as frases ao último span de cada fonte.

**Achados relacionados:** F-07

#### Subtarefas

- [ ] **KS-014.1** Derivar claim e locator da mesma unidade de extração; armazenar doc_revision, offsets, página/bloco e hash do texto de origem.

- [ ] **KS-014.2** Preservar todos os spans por fonte; buscar o span que cobre a frase, em vez de sobrescrever via dict de source_id.

- [ ] **KS-014.3** Quando a frase não estiver em janela recuperada, extrair novo span verificável ou deixar claim explicitamente sem suporte.

- [ ] **KS-014.4** Distinguir texto bruto, texto extraído e normalizado; validar que slice(texto_extraido, offsets) é exatamente verbatim_span.

- [ ] **KS-014.5** Testar frases distantes no mesmo documento, NFKC que altera tokens, CRLF, quebras de página e tabelas.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-014-1** (`test_ks_014_1`): Duas claims em regiões distintas do mesmo documento apontam para spans distintos e corretos.

- **AT-014-2** (`test_ks_014_2`): Mover ou alterar a evidência invalida a referência antiga em vez de manter verified=true.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-015 — Não confundir cobertura lexical com cobertura de pesquisa

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-003, KS-014

**Correspondência com roadmap anterior:** SW-08, SW-11

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/retrieval.py`

**Novos caminhos propostos:** `tests/regression/test_real_coverage.py`

**Motivação:** O runner envia proporção de termos do objetivo como critical_claim_coverage e unresolved_blockers=0.

**Achados relacionados:** F-08

#### Subtarefas

- [ ] **KS-015.1** Renomear o indicador lexical existente para lexical_query_coverage e conservá-lo apenas como diagnóstico barato.

- [ ] **KS-015.2** Criar requisitos/subperguntas explícitos, peso de criticidade e vínculo com claims/evidências que respondem cada requisito.

- [ ] **KS-015.3** Calcular cobertura com base em requisitos atendidos, insuficientes, contraditos ou impossíveis de verificar; preservar o denominador original.

- [ ] **KS-015.4** Consultar bloqueios reais do registry de claims e de extração antes de parar o retrieval.

- [ ] **KS-015.5** Distinguir parada por sucesso, saturação, budget, indisponibilidade e cancelamento; todas geram rationale e lacunas.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-015-1** (`test_ks_015_1`): Repetir todas as palavras do objetivo em fonte irrelevante não produz cobertura completa.

- **AT-015-2** (`test_ks_015_2`): Uma exigência crítica ainda aberta impede stop por suficiência, salvo política explícita de abstenção.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-016 — Conectar counterevidence persistida ao standing

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-014, KS-015

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/verification.py`, `src/kdrx/claims.py`

**Novos caminhos propostos:** `tests/regression/test_counterevidence_feedback.py`

**Motivação:** O runner grava counter_hits, mas o cálculo seguinte de contra edges usa pares entre claims existentes; hits não são integrados nesse caminho.

**Achados relacionados:** F-08

#### Subtarefas

- [ ] **KS-016.1** Converter cada hit candidato em SourceRecord/EvidenceSpan verificáveis, sem presumir que um resultado de busca contradiz a claim.

- [ ] **KS-016.2** Aplicar verificação de entidade, tempo, população, unidade e relação semântica à evidência candidata.

- [ ] **KS-016.3** Persistir edges CONTRADICTS, QUALIFIES ou IRRELEVANT com rationale e versão do verificador.

- [ ] **KS-016.4** Recomputar o standing das claims afetadas e propagar a mudança às seções dependentes.

- [ ] **KS-016.5** Registrar hits rejeitados com motivo e orçamento consumido para evitar repetir a mesma falsa contradição.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-016-1** (`test_ks_016_1`): Contraevidência válida encontrada fora do conjunto original altera a conclusão ou gera conflito explícito.

- **AT-016-2** (`test_ks_016_2`): Um estudo sobre outra população não derruba automaticamente a claim original.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-017 — Fechar SSRF e limites de leitura antes de liberar rede

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-001

**Correspondência com roadmap anterior:** SW-13

**Arquivos atuais afetados:** `src/kdrx/adapters.py`, `src/kdrx/security.py`

**Novos caminhos propostos:** `src/kdrx/tools/http_policy.py`, `tests/security/test_http_policy.py`

**Motivação:** O transporte verifica host inicial e segue redirects via urllib; não aplica limites de bytes nem bloqueio de redes internas no caminho inspecionado.

**Achados relacionados:** F-12

#### Subtarefas

- [ ] **KS-017.1** Permitir somente esquemas autorizados; normalizar hostname/porta e rejeitar userinfo e destinos especiais não autorizados.

- [ ] **KS-017.2** Resolver e bloquear loopback, redes privadas/link-local e endpoints de metadata; validar todos os endereços retornados e o endereço realmente conectado.

- [ ] **KS-017.3** Revalidar cada redirect, limitar saltos e remover Authorization ao mudar de origem; impedir bypass por DNS rebinding.

- [ ] **KS-017.4** Limitar bytes comprimidos/descomprimidos, tipo de conteúdo, tempo total e tempo por fase; interromper stream que exceda o limite.

- [ ] **KS-017.5** Aplicar a política no transporte compartilhado e no proxy de egress do sandbox, não apenas em prompts ou num gate pós-download.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-017-1** (`test_ks_017_1`): Servidor permitido redireciona para metadata/local: request é bloqueado sem leitura.

- **AT-017-2** (`test_ks_017_2`): Resposta infinita ou descompressão excessiva termina no limite e deixa erro tipado.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-018 — Eliminar shell frágil e corrida no arquivo de objetivo

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia do kernel + QA

**Depende de:** KS-003, KS-009

**Correspondência com roadmap anterior:** SW-02, SW-13

**Arquivos atuais afetados:** `plugins/kdr-x/workflows/kdr-deep-research.js`, `plugins/kdr-x/workflows/kdr-run.js`, `plugins/kdr-x/workflows/kdr-plan.js`

**Novos caminhos propostos:** `tests/security/test_command_transport.py`

**Motivação:** Objetivo já usa arquivo, mas diretórios aparecem em strings de comandos e .kdr-objective.txt é compartilhado no outRoot.

#### Subtarefas

- [ ] **KS-018.1** Passar argumentos estruturados ao broker/sidecar e executar binário com argv, sem shell=True e sem interpolar caminhos em comandos de texto.

- [ ] **KS-018.2** Gerar arquivo de requisição exclusivo por run com criação exclusiva e permissões restritas; nunca reutilizar .kdr-objective.txt global.

- [ ] **KS-018.3** Validar run_dir no kernel e resolver caminho a partir de run_id autenticado, não de texto produzido por agente.

- [ ] **KS-018.4** Tratar stdout como protocolo JSON versionado e stderr como diagnóstico; exit code vem do processo observado pelo broker.

- [ ] **KS-018.5** Adicionar testes com espaços, aspas, metacaracteres, Unicode e Windows; transportar objetivo literalmente, sem replace que apague caracteres.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-018-1** (`test_ks_018_1`): Dois planejamentos simultâneos mantêm objetivos e destinos separados.

- **AT-018-2** (`test_ks_018_2`): Um caminho contendo metacaracteres é tratado como um argumento literal e não executa comandos extras.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


## B — Runtime durável e agentes


### KS-019 — Extrair fronteiras internas sem reescrita total

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-003, KS-008, KS-010, KS-011

**Correspondência com roadmap anterior:** SW-05

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/cli.py`, `src/kdrx/scheduler.py`, `src/kdrx/state.py`

**Novos caminhos propostos:** `src/kdrx/runtime/ports.py`, `src/kdrx/application/service.py`, `docs/adr/0001-kernel-owner.md`

**Motivação:** O núcleo e os workflows têm responsabilidades sobrepostas; classes e schemas existentes devem ser preservados onde úteis.

**Achados relacionados:** F-18

#### Subtarefas

- [ ] **KS-019.1** Definir portas ExecutionBackend, StateStore, ArtifactStore, ToolBroker, RetrievalProvider e VerificationService, com testes de contrato.

- [ ] **KS-019.2** Criar ApplicationService como dono do ciclo plan/start/claim/commit/resume/verify/seal/cancel.

- [ ] **KS-019.3** Manter arquivos e imports públicos antigos como fachadas durante migração; evitar mover todos os módulos em um único PR.

- [ ] **KS-019.4** Proibir dependências de schemas/domain para CLI, rede ou workflow; resolver ciclos por inversão de dependências.

- [ ] **KS-019.5** Registrar ADR com decisão de monólito modular local-first; serviços distribuídos só entram após uma necessidade medida.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-019-1** (`test_ks_019_1`): A mesma suíte de contratos roda sobre backend offline e backend live.

- **AT-019-2** (`test_ks_019_2`): Importar schemas não inicializa rede, plugin, banco ou execução de agente.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-020 — Substituir read-modify-write de JSON por estado transacional

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-007, KS-009, KS-019

**Correspondência com roadmap anterior:** SW-06

**Arquivos atuais afetados:** `src/kdrx/state.py`, `src/kdrx/native_hooks.py`, `src/kdrx/artifact.py`

**Novos caminhos propostos:** `src/kdrx/runtime/sqlite_store.py`, `src/kdrx/runtime/migrations/`, `tests/runtime/test_store.py`

**Motivação:** Locks atuais são por instância; manifest, eventos e registry podem divergir entre processos concorrentes.

**Achados relacionados:** F-02, F-05

#### Subtarefas

- [ ] **KS-020.1** Implementar SQLite com transações, WAL e política explícita de durabilidade para implantação single-host; usar arquivos em disco local, não assumir segurança em filesystem de rede. Verificar a versão SQLite realmente vinculada ao Python: exigir build com a correção WAL-reset (3.51.3 ou posterior, ou backport explicitamente corrigido como 3.44.6/3.50.7); registrar sqlite3.sqlite_version. Usar transações curtas, um escritor por vez e synchronous=FULL quando perda de energia estiver no contrato.

- [ ] **KS-020.2** Criar tabelas runs, plan_revisions, tasks, attempts, events, artifacts, sessions, budgets e deliveries com chaves e restrições de unicidade.

- [ ] **KS-020.3** Manter JSON/JSONL como exportações ou snapshots legíveis, não segunda autoridade de escrita.

- [ ] **KS-020.4** Migrar runs existentes em transação verificando hashes; manter modo read-only para versão antiga durante rollback.

- [ ] **KS-020.5** Testar integridade, backup, recuperação e atualização de schema após encerramento abrupto e disco cheio.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-020-1** (`test_ks_020_1`): Dois processos atualizam tasks distintas sem perder nenhuma transição.

- **AT-020-2** (`test_ks_020_2`): Banco restaurado e exportações regeneradas representam o mesmo estado comprometido.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-021 — Implementar leases, fencing e eventos sem dupla conclusão

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-020

**Correspondência com roadmap anterior:** SW-06

**Arquivos atuais afetados:** `src/kdrx/scheduler.py`, `src/kdrx/state.py`

**Novos caminhos propostos:** `src/kdrx/runtime/leases.py`, `src/kdrx/runtime/events.py`, `tests/runtime/test_leases.py`

**Motivação:** Execução concorrente precisa distinguir worker vivo, tentativa expirada e resultado atrasado.

**Achados relacionados:** F-02, F-05

#### Subtarefas

- [ ] **KS-021.1** Adquirir task por compare-and-swap transacional com worker_id, attempt_id, lease_until e fencing_token crescente.

- [ ] **KS-021.2** Emitir heartbeats e reconciliar leases expirados sem apagar histórico de tentativas.

- [ ] **KS-021.3** Rejeitar commits com fencing_token antigo, mesmo quando o worker retorna após um retry bem-sucedido.

- [ ] **KS-021.4** Gravar evento e transição de estado na mesma transação; publicar notificações via outbox idempotente.

- [ ] **KS-021.5** Usar sequência persistida por run e event_id globalmente único; consumidores deduplicam eventos repetidos.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-021-1** (`test_ks_021_1`): Dois workers disputam a mesma task e apenas um obtém lease válido.

- **AT-021-2** (`test_ks_021_2`): Worker antigo volta após timeout e não sobrescreve o resultado da nova tentativa.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-022 — Criar staging de artefatos e commit recuperável

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-008, KS-012, KS-020, KS-021

**Correspondência com roadmap anterior:** SW-05, SW-06

**Arquivos atuais afetados:** `src/kdrx/state.py`, `src/kdrx/artifact.py`

**Novos caminhos propostos:** `src/kdrx/runtime/artifact_store.py`, `tests/runtime/test_artifact_commit.py`

**Motivação:** Atomicidade de um rename não cobre conjuntamente arquivos, manifest e registro de execução.

**Achados relacionados:** F-18

#### Subtarefas

- [ ] **KS-022.1** Cada attempt escreve apenas em staging próprio; artefatos publicados são blobs imutáveis por SHA-256.

- [ ] **KS-022.2** Validar, sincronizar os bytes conforme política de durabilidade e mover para armazenamento content-addressed antes de publicar ponteiros.

- [ ] **KS-022.3** Em transação vincular todos os outputs exigidos, hashes, produtor e task_succeeded; nunca publicar metade da entrega.

- [ ] **KS-022.4** Implementar recuperação de blobs órfãos e staging abandonado com período de retenção e referências do banco.

- [ ] **KS-022.5** Normalizar caminhos de saída antes de ownership: aliases como a/../b e b não podem ter donos distintos.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-022-1** (`test_ks_022_1`): Falha entre blob gravado e commit gera órfão recuperável, nunca sucesso parcial.

- **AT-022-2** (`test_ks_022_2`): Duas tasks com caminhos equivalentes são rejeitadas antes de escrever.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-023 — Despachar por capacidade e papel, não por quatro task IDs

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-003, KS-019, KS-021

**Correspondência com roadmap anterior:** SW-04, SW-05

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/scheduler.py`, `plugins/kdr-x/agents/role-resolution.json`

**Novos caminhos propostos:** `src/kdrx/runtime/executors.py`, `tests/runtime/test_executor_registry.py`

**Motivação:** _FileResearchExecutor.__call__ reconhece apenas T-RETRIEVE, T-VERIFY, T-SYNTHESIZE e T-INTEGRITY.

**Achados relacionados:** F-01, F-03

#### Subtarefas

- [ ] **KS-023.1** Introduzir task.kind ou capability_key validada, independente do identificador único da tarefa.

- [ ] **KS-023.2** Registrar executores para retrieval, source verification, claim analysis, writing, code, artifact export e deterministic gate.

- [ ] **KS-023.3** Manter as quatro tasks da demo como plano de exemplo, não como limites universais de execução.

- [ ] **KS-023.4** Fazer planner verificar disponibilidade de capability antes de aprovar o plano e indicar alternativas explícitas.

- [ ] **KS-023.5** Separar FixtureExecutor de backends produtivos; fixtures nunca são selecionadas por fallback automático de erro live.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-023-1** (`test_ks_023_1`): Plano aprovado com IDs arbitrários e capacidades registradas executa corretamente.

- **AT-023-2** (`test_ks_023_2`): Capacidade inexistente bloqueia planejamento com mensagem acionável, sem falhar tarde como unknown task.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-024 — Materializar especialização e privilégio mínimo por tarefa

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-003, KS-008, KS-023

**Correspondência com roadmap anterior:** SW-04

**Arquivos atuais afetados:** `src/kdrx/schemas/plan.py`, `plugins/kdr-x/agents/role-resolution.json`, `plugins/kdr-x/agents/`

**Novos caminhos propostos:** `src/kdrx/runtime/execution_spec.py`, `tests/contracts/test_execution_spec.py`

**Motivação:** Arquivos de agentes não garantem que role, ferramentas, contexto e restrições cheguem à execução real.

**Achados relacionados:** F-01, F-03

#### Subtarefas

- [ ] **KS-024.1** Construir AgentExecutionSpec com papel resolvido, versão do prompt, modelo, esforço, ferramentas, skills, deadline, cwd e política de contexto.

- [ ] **KS-024.2** Distinguir workspace de projeto somente leitura de diretório autorizado de outputs; read_only não significa proibir o agente de produzir seu próprio resultado.

- [ ] **KS-024.3** Exigir identidade diferente para writer e reviewer e, nas claims críticas, permitir verificador independente do modelo gerador.

- [ ] **KS-024.4** Validar compatibilidade de tools e schema com cada backend sem simplesmente aceitar campos ignorados pelo provedor.

- [ ] **KS-024.5** Persistir a especificação efetivamente aplicada e capability restrictions para auditoria de cada attempt.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-024-1** (`test_ks_024_1`): Trace comprova que search e coder receberam permissões distintas, não apenas prompts distintos.

- **AT-024-2** (`test_ks_024_2`): Revisor não consegue aprovar output que ele mesmo produziu sob outro nome de tarefa.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-025 — Implementar um backend live real e portável

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-017, KS-018, KS-021, KS-024, KS-031

**Correspondência com roadmap anterior:** SW-04, SW-05

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `plugins/kdr-x/workflows/`

**Novos caminhos propostos:** `src/kdrx/runtime/backends/claude.py`, `src/kdrx/runtime/backends/protocol.py`, `tests/live/test_backend.py`

**Motivação:** É necessário um adaptador real entre kernel e harness, sem pressupor acesso a filesystem diretamente no JavaScript de workflow.

**Achados relacionados:** F-03

#### Subtarefas

- [ ] **KS-025.1** Escolher como primeira implementação uma interface oficialmente suportada de execução de agentes; fixar versão e registrar capabilities detectadas.

- [ ] **KS-025.2** Transportar entradas e resultados por protocolo estruturado, registrando tool calls observadas, uso de tokens e encerramento do processo.

- [ ] **KS-025.3** Não usar texto gerado pelo modelo como prova de exit code, hash, task commit ou gasto real.

- [ ] **KS-025.4** Conectar cancelamento/deadline do kernel ao processo/harness e reportar limitações que não possam ser garantidas pelo backend.

- [ ] **KS-025.5** Manter contrato independente de fabricante para acrescentar outros backends posteriormente sem duplicar estado ou gates.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-025-1** (`test_ks_025_1`): Uma tarefa real produz artefato validado e trace de chamada ao provedor, sem FixtureExecutor.

- **AT-025-2** (`test_ks_025_2`): Resposta truncada, erro de autenticação e saída fora de schema são classificados e não convertidos em sucesso.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-026 — Reduzir workflows a fachadas do kernel

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-010, KS-018, KS-023, KS-025, KS-030

**Correspondência com roadmap anterior:** SW-05

**Arquivos atuais afetados:** `plugins/kdr-x/workflows/kdr-plan.js`, `plugins/kdr-x/workflows/kdr-run.js`, `plugins/kdr-x/workflows/kdr-verify.js`, `plugins/kdr-x/workflows/kdr-deep-research.js`

**Novos caminhos propostos:** `tests/live/test_workflow_kernel_parity.py`

**Motivação:** As quatro entradas precisam compartilhar plano, commits e resultado final, respeitando as limitações do host de workflows.

**Achados relacionados:** F-03

#### Subtarefas

- [ ] **KS-026.1** Fazer toda alteração de estado passar por ApplicationService/broker; o JavaScript apenas coordena chamadas suportadas e apresenta progresso.

- [ ] **KS-026.2** Transportar run_id/revision e recibos do kernel; qualquer JSON devolvido por agente deve ser revalidado contra o registry, não tratado como autorização.

- [ ] **KS-026.3** Eliminar agentes cujo único papel é ler JSON, verificar existência de arquivo ou interpretar status que o kernel pode calcular.

- [ ] **KS-026.4** Quando o workflow não puder executar determinada operação diretamente, usar backend/sidecar autorizado; não introduzir require, import ou filesystem no corpo proibido.

- [ ] **KS-026.5** Unificar standalone e deep-research em contratos equivalentes, incluindo comportamento de null, cancelamento, resume e selo final.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-026-1** (`test_ks_026_1`): CLI e workflow executam o mesmo plano/hash e chegam ao mesmo estado final.

- **AT-026-2** (`test_ks_026_2`): Um agente inventa passed=true: sem recibo de commit do kernel o run permanece bloqueado.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-027 — Executar DAG com concorrência real e prontidão por dependência

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-021, KS-022, KS-023

**Correspondência com roadmap anterior:** SW-06

**Arquivos atuais afetados:** `src/kdrx/scheduler.py`, `src/kdrx/dag.py`

**Novos caminhos propostos:** `src/kdrx/runtime/async_scheduler.py`, `tests/runtime/test_concurrency.py`

**Motivação:** WaveScheduler executa sequencialmente; barreiras globais de wave podem atrasar ramos independentes.

**Achados relacionados:** F-01

#### Subtarefas

- [ ] **KS-027.1** Implementar fila ready baseada em dependências satisfeitas e leases, com concorrência limitada configurável.

- [ ] **KS-027.2** Usar asyncio para I/O e isolamento de processos para trabalho bloqueante; não pressupor que cancelar uma coroutine interrompe threads ou subprocessos.

- [ ] **KS-027.3** Começar com limite operacional conservador de 8; limitar backend Claude workflow à capacidade oficialmente anunciada, no máximo 16 concorrentes.

- [ ] **KS-027.4** Liberar descendente assim que seus próprios pais concluírem, sem esperar por irmãos não relacionados; waves permanecem visualização.

- [ ] **KS-027.5** Medir sobreposição real de execução, caminho crítico, fila e ociosidade; preservar resultados determinísticos para operações puras.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-027-1** (`test_ks_027_1`): Com limite 4, quatro tarefas artificiais independentes se sobrepõem e nunca aparecem cinco simultâneas.

- **AT-027-2** (`test_ks_027_2`): Ramo independente continua após falha de outro ramo; apenas dependentes ficam bloqueados.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-028 — Aplicar retries, deadline e cancelamento no efeito real

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-021, KS-025, KS-027

**Correspondência com roadmap anterior:** SW-06

**Arquivos atuais afetados:** `src/kdrx/scheduler.py`, `src/kdrx/schemas/plan.py`

**Novos caminhos propostos:** `src/kdrx/runtime/retry_policy.py`, `tests/runtime/test_cancellation.py`

**Motivação:** Capturar toda Exception e repetir imediatamente não distingue falha permanente de rate limit ou efeito parcialmente executado.

**Achados relacionados:** F-01

#### Subtarefas

- [ ] **KS-028.1** Classificar erros de auth/schema/policy como não retentáveis; 429 e indisponibilidade transitória podem respeitar Retry-After e backoff com jitter.

- [ ] **KS-028.2** Limitar tentativas e tempo global da tarefa, não apenas timeout individual; o tempo de espera também consome deadline.

- [ ] **KS-028.3** Propagar cancelamento a tool calls e processos filhos, confirmar término e invalidar lease antes de abrir nova tentativa.

- [ ] **KS-028.4** Usar idempotency key para operações externas compatíveis e reconciliação quando o provedor não permite saber se o efeito ocorreu.

- [ ] **KS-028.5** Salvar dead-letter com erro sanitizado e alternativas; não prometer exactly-once universal para serviços externos.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-028-1** (`test_ks_028_1`): Credencial inválida não dispara dezenas de retries; 429 respeita limite e política.

- **AT-028-2** (`test_ks_028_2`): Cancelar tarefa interrompe efeitos ou sinaliza explicitamente operação externa não cancelável, sem marcá-la como inexistente.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-029 — Controlar orçamento compartilhado antes de gastar

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-003, KS-020, KS-025, KS-027

**Correspondência com roadmap anterior:** SW-07, SW-14

**Arquivos atuais afetados:** `src/kdrx/schemas/plan.py`, `src/kdrx/scheduler.py`

**Novos caminhos propostos:** `src/kdrx/runtime/budget_ledger.py`, `tests/runtime/test_budget.py`

**Motivação:** Budget existe no schema, mas não é enforcement no scheduler inspecionado.

**Achados relacionados:** F-01

#### Subtarefas

- [ ] **KS-029.1** Reservar orçamento atomicamente antes de model/tool call e reconciliar com uso real retornado pelo provedor.

- [ ] **KS-029.2** Controlar tokens de entrada/saída/cache, dinheiro, consultas, downloads, concorrência e tempo por run/task/provider.

- [ ] **KS-029.3** Versionar tabela de preços e armazenar fonte/data; registrar estimativa separada de cobrança efetivamente observável.

- [ ] **KS-029.4** Aplicar semáforos de rate limit globais para múltiplos agentes e backpressure quando reservas esgotarem.

- [ ] **KS-029.5** Parar novas chamadas no limite e gerar relatório de lacunas; limitar overshoot de chamadas já em voo por reserva conservadora.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-029-1** (`test_ks_029_1`): Múltiplos workers não ultrapassam coletivamente o orçamento por uma corrida de saldo.

- **AT-029-2** (`test_ks_029_2`): Cache hit, retry e chamada com uso ausente são contabilizados sem duplicação ou custo fictício zero.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-030 — Fortalecer hooks nativos e registry de sessões

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-020, KS-021, KS-024

**Correspondência com roadmap anterior:** SW-00

**Arquivos atuais afetados:** `src/kdrx/native_hooks.py`, `src/kdrx/hook_dispatch.py`, `plugins/kdr-x/hooks/hooks.json`

**Novos caminhos propostos:** `tests/live/test_native_hook_sessions.py`

**Motivação:** O registry atual tem escrita atômica de arquivo, mas load/save sem transação entre sessões; corrupção vira registry vazio.

**Achados relacionados:** F-05

#### Subtarefas

- [ ] **KS-030.1** Migrar session/task/agent bindings para StateStore transacional e vincular explicitamente cada execução ao run.

- [ ] **KS-030.2** Reservar auto-binding por run único apenas como modo compatível observável; não resolver ambiguidade escolhendo arbitrariamente o primeiro run.

- [ ] **KS-030.3** Preservar tolerância a campos adicionais do host, mas falhar com segurança quando falta identidade necessária para autorizar uma ação.

- [ ] **KS-030.4** Tratar registry corrompido como estado degradado que bloqueia ações privilegiadas, não como sessão inocente fora de pesquisa.

- [ ] **KS-030.5** Capturar fixtures reais do host com sanitização; cobrir eventos relevantes e ferramentas de todas as plataformas declaradas.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-030-1** (`test_ks_030_1`): Dois processos de hook mapeiam sessões diferentes sem perder bindings.

- **AT-030-2** (`test_ks_030_2`): Payload incompleto não gera traceback nem permite acesso a run não autorizado.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-031 — Isolar workers e intermediar ferramentas com políticas

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-017, KS-018, KS-019, KS-024

**Correspondência com roadmap anterior:** SW-13

**Arquivos atuais afetados:** `src/kdrx/security.py`, `src/kdrx/hooks.py`, `plugins/kdr-x/agents/`

**Novos caminhos propostos:** `src/kdrx/tools/broker.py`, `src/kdrx/runtime/sandbox.py`, `tests/security/test_worker_isolation.py`

**Motivação:** Regras em prompts e marcadores de nomes de ferramenta não são uma fronteira de segurança suficiente.

**Achados relacionados:** F-12

#### Subtarefas

- [ ] **KS-031.1** Definir sandbox com mounts explícitos: inputs imutáveis, staging da task gravável, demais runs e segredos inacessíveis.

- [ ] **KS-031.2** Aplicar allowlist de ferramentas por capability, caminho e tipo de operação; não usar apenas substring como write/bash.

- [ ] **KS-031.3** Entregar credenciais efêmeras ao broker, não a textos do modelo nem ao ambiente amplo do worker.

- [ ] **KS-031.4** Rotular conteúdo recuperado como dado não confiável; nenhuma instrução nessa fonte pode alterar contrato, budget, policy ou destino.

- [ ] **KS-031.5** Bloquear egress não autorizado no sandbox e testar execução de código com limites de CPU, memória, disco e processos.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-031-1** (`test_ks_031_1`): Prompt injection pode ser lida, mas não consegue alterar plano, gates, orçamento ou obter segredo de outro worker.

- **AT-031-2** (`test_ks_031_2`): Um processo tenta escrever fora do staging ou conectar-se a IP interno: a política do ambiente bloqueia o efeito.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-032 — Revisar plano sem invalidar trabalho corretamente concluído

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-010, KS-020, KS-021, KS-027

**Correspondência com roadmap anterior:** SW-08

**Arquivos atuais afetados:** `src/kdrx/dag.py`, `src/kdrx/runner.py`

**Novos caminhos propostos:** `src/kdrx/runtime/plan_revisions.py`, `tests/runtime/test_plan_revisions.py`

**Motivação:** Replanejamento adaptativo exige histórico e regras explícitas, não substituição informal de waves em memória.

**Achados relacionados:** F-18

#### Subtarefas

- [ ] **KS-032.1** Representar cada mudança como PlanPatch com base_revision, motivo, tasks adicionadas/removidas, deps e orçamento necessário.

- [ ] **KS-032.2** Validar aciclicidade, referências, ownership normalizado e capacidades antes do commit.

- [ ] **KS-032.3** Bloquear alteração de tarefas em voo sem cancelamento/reconciliação; tasks concluídas são imutáveis e substituídas por nova revisão.

- [ ] **KS-032.4** Invalidar somente resultados cujo input hash ou contrato mudou, com propagação aos descendentes.

- [ ] **KS-032.5** Garantir que executor usa a revisão do lease; resposta tardia de plano antigo não contamina o novo plano.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-032-1** (`test_ks_032_1`): Novo conflito cria tarefa de validação e preserva resultados de ramos não afetados.

- **AT-032-2** (`test_ks_032_2`): Dois planejadores propõem patch sobre a mesma revisão: um precisa rebasear antes de aplicar.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-033 — Coordenar agentes com mensagens tipadas e orçamento

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-020, KS-021, KS-027

**Correspondência com roadmap anterior:** SW-09

**Arquivos atuais afetados:** `src/kdrx/artifact.py`, `src/kdrx/schemas/plan.py`

**Novos caminhos propostos:** `src/kdrx/runtime/blackboard.py`, `tests/runtime/test_coordination.py`

**Motivação:** Cooperação útil deve compartilhar evidência necessária sem gerar conversação coletiva ilimitada ou dependências escondidas.

#### Subtarefas

- [ ] **KS-033.1** Criar eventos SourceDiscovered, ClaimChanged, GapOpened, HelpRequested e ArtifactCommitted com refs e escopo.

- [ ] **KS-033.2** Oferecer assinaturas por task/subquestão, deduplicar notificações e limitar taxa/tamanho de mensagens.

- [ ] **KS-033.3** Permitir solicitação direta entre especialistas somente com motivo, budget e prazo; converter dependência resultante em aresta auditável.

- [ ] **KS-033.4** Gerenciar recursos exclusivos com ordem de aquisição e expiração; não usar bloqueios informais em prompts.

- [ ] **KS-033.5** Medir ganho por coordenação contra comunicação desligada; desativar chatter sem contribuição observada.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-033-1** (`test_ks_033_1`): Dois workers descobrem a mesma fonte: registry converge sem trabalho duplicado posterior desnecessário.

- **AT-033-2** (`test_ks_033_2`): Solicitações circulares não geram deadlock e deixam diagnóstico de dependência.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-034 — Fechar o primeiro E2E live realmente unificado

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Runtime + segurança

**Depende de:** KS-007, KS-011, KS-012, KS-013, KS-014, KS-016, KS-025, KS-026, KS-027, KS-028, KS-029, KS-030, KS-031

**Correspondência com roadmap anterior:** SW-05

**Arquivos atuais afetados:** `tests/test_workflows.py`, `src/kdrx/cli.py`, `plugins/kdr-x/workflows/`

**Novos caminhos propostos:** `tests/live/test_research_journey.py`, `evidence/live-run-manifest.schema.json`

**Motivação:** O teste estrutural de workflow explicitamente não executa o runtime real.

**Achados relacionados:** F-03, F-16

#### Subtarefas

- [ ] **KS-034.1** Executar pergunta fixa com pesquisa, leitura, verificação, escrita e auditoria usando ao menos cinco especialistas reais em funções distintas.

- [ ] **KS-034.2** Registrar proof-of-execution de cada chamada, artefatos e hashes, sem gravar credenciais ou raciocínio privado do modelo.

- [ ] **KS-034.3** Interromper após retrieval e retomar em sessão/processo novo, comprovando não repetição das tasks comprometidas.

- [ ] **KS-034.4** Repetir o mesmo cenário por CLI e fachada plugin e comparar contratos, integridade e resultado de entrega.

- [ ] **KS-034.5** Bloquear promoção de funcionalidade live sem esse percurso passar com orçamento conhecido e sem mocks na fronteira com host/provedor.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-034-1** (`test_ks_034_1`): Trace prova chamadas reais, paralelismo onde pertinente, commits e selo final; nenhuma etapa apenas alega ter ocorrido.

- **AT-034-2** (`test_ks_034_2`): Falha de provedor gera estado parcial recuperável e relatório não aprovado, nunca sucesso fictício.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


## C — Pesquisa e capacidades reais


### KS-035 — Padronizar transportes e resultados de adapters

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-017, KS-019, KS-029

**Correspondência com roadmap anterior:** SW-05, SW-11

**Arquivos atuais afetados:** `src/kdrx/adapters.py`, `src/kdrx/schemas/corpus.py`

**Novos caminhos propostos:** `src/kdrx/tools/http_transport.py`, `tests/contracts/test_adapters.py`

**Motivação:** Adapters retornam formatos heterogêneos e o transporte atual decodifica qualquer resposta como texto.

**Achados relacionados:** F-12, F-13

#### Subtarefas

- [ ] **KS-035.1** Criar FetchResponse com bytes, status, headers relevantes, URL final, redirect chain, timing e hash; parser de formato fica separado.

- [ ] **KS-035.2** Padronizar erros rate_limited, unauthorized, not_found, parse_failed, policy_blocked e provider_unavailable.

- [ ] **KS-035.3** Implementar cache condicional, paginação explícita, idempotência de buscas e limites de resultados/custo.

- [ ] **KS-035.4** Usar fixtures reais sanitizadas de contratos HTTP e detecção de schema drift; ausência de campo opcional não derruba todo o lote.

- [ ] **KS-035.5** Persistir fonte apenas após identidade e conteúdo mínimo validáveis; metadados sem full text não viram evidência de leitura.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-035-1** (`test_ks_035_1`): JSON inválido ou mudança de schema produz erro tipado com proveniência.

- **AT-035-2** (`test_ks_035_2`): Resposta binária preserva bytes e metadados sem decode UTF-8 destrutivo.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-036 — Robustecer OpenAlex e cobertura de literatura

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-035

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/adapters.py`, `tests/test_adapters.py`

**Novos caminhos propostos:** `tests/contracts/test_openalex.py`

**Motivação:** OpenAlexAdapter encadeia .get sobre primary_location.source, que pode receber None no limite de entrada.

**Achados relacionados:** F-13

#### Subtarefas

- [ ] **KS-036.1** Tratar primary_location e source como opcionais independentes; normalizar authors, título, datas e identificadores ausentes.

- [ ] **KS-036.2** Adicionar paginação/cursor conforme contrato atual oficialmente verificado e parâmetros de autenticação/quota configuráveis.

- [ ] **KS-036.3** Separar busca de metadados da obtenção autorizada de conteúdo; registrar abstract-only e full-text como níveis distintos.

- [ ] **KS-036.4** Preservar DOI, ID externo, versão e link canônico sem confundir identidade da obra com uma localização.

- [ ] **KS-036.5** Adicionar testes com source null, campos ausentes, página vazia, 429 e respostas com obras duplicadas.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-036-1** (`test_ks_036_1`): Payload válido com source=null não interrompe o lote.

- **AT-036-2** (`test_ks_036_2`): Resultados além da primeira página são coletados sem duplicatas e respeitando budget.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-037 — Preservar datas e versões em DOI, Crossref e arXiv

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-035

**Correspondência com roadmap anterior:** SW-11, SW-15

**Arquivos atuais afetados:** `src/kdrx/adapters.py`, `src/kdrx/verification.py`

**Novos caminhos propostos:** `tests/contracts/test_scholarly_identity.py`

**Motivação:** CrossrefAdapter reduz issued a 1º de janeiro do ano; incerteza e precisão de datas devem ser preservadas.

**Achados relacionados:** F-13

#### Subtarefas

- [ ] **KS-037.1** Representar data com precisão year/month/day e não inventar dia ou mês quando não fornecidos.

- [ ] **KS-037.2** Verificar DOI resolvido contra título/autoria/obra esperada, distinguindo redirect legítimo de obra errada.

- [ ] **KS-037.3** Preservar versões arXiv e vínculo preprint/publicação; não contar a mesma obra como duas evidências independentes.

- [ ] **KS-037.4** Integrar estado de retratação/correção com fonte e timestamp de consulta e TTL da verificação.

- [ ] **KS-037.5** Deixar indisponibilidade do resolvedor como unverified/retryable, não como prova de fonte fabricada.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-037-1** (`test_ks_037_1`): Data 2026-07-23 permanece completa; somente 2026 permanece precisão de ano.

- **AT-037-2** (`test_ks_037_2`): DOI real que resolve para outra obra não passa como evidência da obra alegada.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-038 — Pesquisar código com identidade de commit e conteúdo

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-035, KS-031

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/adapters.py`, `plugins/github/kimi.plugin.json`

**Novos caminhos propostos:** `src/kdrx/research/code_sources.py`, `tests/contracts/test_github_sources.py`

**Motivação:** Pesquisa de código precisa fixar versão, respeitar autorização e distinguir metadados de leitura de implementação.

#### Subtarefas

- [ ] **KS-038.1** Exigir owner/repo/ref/path em API tipada e fixar commit SHA na ingestão; branch móvel fica apenas como informação de origem.

- [ ] **KS-038.2** Paginar árvores, blobs e resultados; detectar truncation, arquivos grandes, submodules e LFS sem fingir que bytes ausentes foram lidos.

- [ ] **KS-038.3** Preservar trecho com linhas e blob SHA para citações de código e separar README declarativo de execução/testes.

- [ ] **KS-038.4** Aplicar autorização do usuário e egress no broker; nunca exibir tokens nem repassá-los ao agente escritor.

- [ ] **KS-038.5** Criar modo read-only por padrão e exigir aprovação explícita para commits/push/PR em tarefas que autorizem escrita.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-038-1** (`test_ks_038_1`): Mudança de main durante o run não mistura versões no relatório.

- **AT-038-2** (`test_ks_038_2`): Arquivo LFS não disponível é marcado não inspecionado, e não como fonte integralmente lida.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-039 — Adicionar busca web e navegador como capacidades distintas

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-031, KS-035

**Correspondência com roadmap anterior:** SW-05, SW-11, SW-13

**Arquivos atuais afetados:** `src/kdrx/adapters.py`, `plugins/kdr-x/agents/search.md`

**Novos caminhos propostos:** `src/kdrx/research/web_search.py`, `src/kdrx/tools/browser.py`, `tests/live/test_web_retrieval.py`

**Motivação:** WebFetch não substitui um mecanismo de busca; presença de adapters acadêmicos também não equivale à rota web integrada.

**Achados relacionados:** F-12

#### Subtarefas

- [ ] **KS-039.1** Implementar provedor de busca autorizado e configurável com query, idioma, período, tipo de fonte e paginação.

- [ ] **KS-039.2** Usar fetch direto primeiro e navegador isolado quando JavaScript/autenticação autorizada forem realmente necessários.

- [ ] **KS-039.3** Registrar URL, trecho retornado, consulta e posição; abrir a fonte antes de transformar snippet em evidência forte.

- [ ] **KS-039.4** Respeitar acesso e termos do provedor, sem contornar login, captcha ou paywall; registrar limitações de acesso.

- [ ] **KS-039.5** Deduplicar consultas em voo e planejar consultas complementares por lacuna, não replicar a mesma busca em todos os agentes.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-039-1** (`test_ks_039_1`): Uma pergunta sem arquivos locais é respondida pelo pipeline com fontes abertas e rastreáveis.

- **AT-039-2** (`test_ks_039_2`): Snippet não confirmado permanece indicação de busca e não suporta sozinho uma claim crítica.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-040 — Criar snapshots imutáveis com proveniência de extração

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-013, KS-022, KS-035

**Correspondência com roadmap anterior:** SW-10, SW-11

**Arquivos atuais afetados:** `src/kdrx/corpus.py`, `src/kdrx/retrieval.py`, `src/kdrx/schemas/corpus.py`

**Novos caminhos propostos:** `src/kdrx/research/snapshots.py`, `tests/research/test_snapshots.py`

**Motivação:** Um hash de texto normalizado não identifica sozinho os bytes originais, transformação aplicada e fonte revisitada.

**Achados relacionados:** F-13

#### Subtarefas

- [ ] **KS-040.1** Armazenar raw_bytes_hash e extracted_text_hash separadamente, com extractor_name/version/config e codificação.

- [ ] **KS-040.2** Preservar URL original/final, retrieved_at, published_at quando conhecido, precisão de data e direitos de uso.

- [ ] **KS-040.3** Gerar doc_revision imutável por versão do conteúdo, sem sobrescrever evidências de relatórios anteriores.

- [ ] **KS-040.4** Criar mapa de coordenadas bruto/extraído/bloco/página para citações reproduzíveis e recortes visuais.

- [ ] **KS-040.5** Implementar retenção por política, remoção autorizada e tombstones sem quebrar silenciosamente lineage histórica.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-040-1** (`test_ks_040_1`): Reexecução sobre snapshot congelado encontra os mesmos trechos e hashes.

- **AT-040-2** (`test_ks_040_2`): Fonte externa mudou: nasce nova revisão e o relatório antigo continua ligado à versão originalmente consultada.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-041 — Extrair documentos preservando tabelas, código e coordenadas

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-005, KS-014, KS-040

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/extractors.py`, `src/kdrx/retrieval.py`, `pyproject.toml`

**Novos caminhos propostos:** `src/kdrx/research/document_ir.py`, `tests/research/test_document_ir.py`

**Motivação:** O extractor Markdown remove code fences; PDF concatena texto e não devolve localizadores de página ou tabela.

**Achados relacionados:** F-13

#### Subtarefas

- [ ] **KS-041.1** Introduzir DocumentIR com blocos de texto, código, tabela, figura e coordenadas; cada bloco referencia os bytes da fonte.

- [ ] **KS-041.2** Preservar código em Markdown e links com contexto, em vez de apagá-los de um corpus destinado também a pesquisa de software.

- [ ] **KS-041.3** Oferecer dependências opcionais declaradas para PDF/Office e probes no doctor; documento escaneado sem texto não conta como extração bem-sucedida.

- [ ] **KS-041.4** Extrair tabelas mantendo cabeçalhos/unidades e usar leitura visual/OCR apenas quando necessário, registrando método e confiança.

- [ ] **KS-041.5** Criar fixtures de duas colunas, tabela multipágina, caracteres Unicode, páginas vazias, PDF criptografado e documentos corrompidos.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-041-1** (`test_ks_041_1`): Uma claim numérica de tabela é reproduzível por página, célula e cabeçalho.

- **AT-041-2** (`test_ks_041_2`): README com código e PDF sem camada textual não entram no índice como prosa truncada supostamente completa.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-042 — Adicionar retrieval semântico mensurável sem remover BM25

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-035, KS-040, KS-041, KS-006

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/retrieval.py`, `src/kdrx/corpus.py`

**Novos caminhos propostos:** `src/kdrx/research/embeddings.py`, `src/kdrx/research/reranker.py`, `tests/research/test_hybrid_retrieval.py`

**Motivação:** O canal dense atual é cosseno de n-gramas, explicitamente não um embedding neural.

**Achados relacionados:** F-11

#### Subtarefas

- [ ] **KS-042.1** Manter BM25 como baseline e fallback identificado; implementar interface de embedding com modelo/versão/dimensão registrados.

- [ ] **KS-042.2** Indexar chunks estruturais e armazenar chave snapshot+chunk+embedding_version para invalidação correta.

- [ ] **KS-042.3** Combinar lexical e vetorial por rank fusion e aplicar reranker apenas aos candidatos necessários.

- [ ] **KS-042.4** Calibrar top-k, chunking e orçamento por categoria/idioma usando conjunto de desenvolvimento, nunca o heldout final.

- [ ] **KS-042.5** Medir recall de evidência relevante, precisão após rerank e custo/latência; ativar neural somente onde supera o baseline sem regressões críticas.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-042-1** (`test_ks_042_1`): Consulta em português recupera evidência equivalente em inglês sem depender de palavras iguais.

- **AT-042-2** (`test_ks_042_2`): Modo neural desligado continua explícito e reproduzível; não rotula n-gramas como embeddings.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-043 — Evitar deduplicação destrutiva e aliases semânticos de URL

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-013, KS-040

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/corpus.py`, `src/kdrx/runner.py`

**Novos caminhos propostos:** `tests/research/test_source_dedup.py`

**Motivação:** canonicalize_url remove ref/source genericamente, e near-dedupe usa título; parâmetros podem representar versão ou conteúdo real.

**Achados relacionados:** F-18

#### Subtarefas

- [ ] **KS-043.1** Separar normalização conservadora de URL de remoção de tracking específica por domínio e política.

- [ ] **KS-043.2** Preservar query params semanticamente relevantes, fragments que localizam evidência e versões de repositório/documento.

- [ ] **KS-043.3** Distinguir mesmo conteúdo, mesma obra, versões da obra e mesma família de dependência; não usar um único hash para todas essas relações.

- [ ] **KS-043.4** Preservar todos os aliases e metadados de proveniência mesmo quando indexação deduplica bytes.

- [ ] **KS-043.5** Adicionar casos de títulos iguais para trabalhos distintos, versões divergentes, republicações e URLs cujo ref altera conteúdo.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-043-1** (`test_ks_043_1`): Duas versões materialmente distintas não colapsam por terem título ou caminho parecidos.

- **AT-043-2** (`test_ks_043_2`): Cinco republicações idênticas podem compartilhar conteúdo, sem apagar a informação de onde cada uma foi encontrada.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-044 — Planejar consultas por lacuna, idioma e tempo

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-015, KS-039, KS-042

**Correspondência com roadmap anterior:** SW-08, SW-11

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/retrieval.py`, `src/kdrx/schemas/request.py`

**Novos caminhos propostos:** `src/kdrx/research/query_planner.py`, `tests/research/test_queries.py`

**Motivação:** _build_query_graph divide frases por and/pontuação e o contrato de exemplo fixa inglês.

**Achados relacionados:** F-08

#### Subtarefas

- [ ] **KS-044.1** Extrair entidades, subquestões, hipóteses, contrafactuais e critérios do pedido usando schema e validação humana/opcional conforme contrato.

- [ ] **KS-044.2** Preservar idioma de resposta e idiomas de busca; incluir português sem inferir que traduzir palavras equivale a verificar fatos.

- [ ] **KS-044.3** Gerar consultas complementares para origem primária, implementação, resultados negativos, limitações e datas relevantes.

- [ ] **KS-044.4** Versionar queries e vincular cada uma ao requisito que pretende resolver; deduplicar consultas equivalentes.

- [ ] **KS-044.5** Executar follow-up apenas quando existe lacuna útil ou contradição, com budget e critério de parada declarados.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-044-1** (`test_ks_044_1`): Pedido com cinco critérios produz cinco requisitos rastreáveis e pesquisas adequadas, não apenas divisão por pontuação.

- **AT-044-2** (`test_ks_044_2`): Pergunta sobre estado atual não usa silenciosamente fonte antiga como única autoridade.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-045 — Auditar e normalizar os oito plugins externos ao kdr-x

**Prioridade:** P0 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-004, KS-031, KS-035

**Correspondência com roadmap anterior:** SW-01, SW-13, SW-17

**Arquivos atuais afetados:** `plugins/github/`, `plugins/scholar/`, `plugins/sec_edgar/`, `plugins/imf/`, `plugins/world_bank_open_data/`, `plugins/yahoo_finance/`, `plugins/image_generation/`, `plugins/audio_generation/`

**Novos caminhos propostos:** `plugins/external-providers.lock.json`, `tests/plugins/test_external_capabilities.py`

**Motivação:** Inventário de diretórios não comprova autenticação, compatibilidade de SDK nem autorização de distribuição.

**Achados relacionados:** F-15

#### Subtarefas

- [ ] **KS-045.1** Inspecionar todos os scripts, manifests, skills e bundles; comparar arquivo por arquivo entre arquivo compactado e árvore expandida.

- [ ] **KS-045.2** Classificar chamada de API pública, gateway Kimi e provedor substituto; documentar como obter acesso autorizado sem pressupor ambiente proprietário.

- [ ] **KS-045.3** Criar contrato comum ProviderCapability com estado de disponibilidade e limites observáveis.

- [ ] **KS-045.4** Desabilitar por padrão provedores não testados ou sem licença resolvida; não os instalar implicitamente no comando principal.

- [ ] **KS-045.5** Gerar testes de descoberta, autorização, retorno tipado, falha de dependência e ausência de dados para cada integração liberada.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-045-1** (`test_ks_045_1`): Cada um dos nove diretórios totais possui status inequívoco e justificativa de distribuição.

- **AT-045-2** (`test_ks_045_2`): Ausência de SDK/token resulta em capability indisponível, não em tentativa de fabricar a resposta esperada.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-046 — Tornar geração de imagem e áudio independente de instalação mutável

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-035, KS-045

**Correspondência com roadmap anterior:** SW-01, SW-13

**Arquivos atuais afetados:** `plugins/image_generation/scripts/image_generation_tool.py`, `plugins/audio_generation/`

**Novos caminhos propostos:** `src/kdrx/tools/media_provider.py`, `tests/plugins/test_media_providers.py`

**Motivação:** O script de imagens busca latest.url em manifest CDN e executa pip install -U --user; isso não produz ambiente reprodutível.

**Achados relacionados:** F-15

#### Subtarefas

- [ ] **KS-046.1** Remover instalação automática de latest durante execução produtiva; resolver dependências no build com versão e hashes fixados.

- [ ] **KS-046.2** Isolar SDK em ambiente próprio e registrar origem/verificação do wheel; não alterar pacotes do usuário implicitamente.

- [ ] **KS-046.3** Implementar interface autorizada de geração/upload/download com limites de tamanho, MIME e custo.

- [ ] **KS-046.4** Tratar upload de arquivo privado como saída de dados que exige política explícita; não registrar signed URLs duradouras em logs públicos.

- [ ] **KS-046.5** Validar bytes finais de mídia, dimensões/duração quando aplicáveis, hash e referência de tarefa que os gerou.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-046-1** (`test_ks_046_1`): Duas instalações da mesma release usam exatamente a mesma dependência, sem consulta a latest.

- **AT-046-2** (`test_ks_046_2`): Falha de gateway não deixa arquivo falso de imagem/áudio nem sucesso declarado.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-047 — Validar dados financeiros, econômicos e acadêmicos por contrato

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-035, KS-037, KS-045

**Correspondência com roadmap anterior:** SW-11, SW-13

**Arquivos atuais afetados:** `plugins/imf/`, `plugins/sec_edgar/`, `plugins/world_bank_open_data/`, `plugins/yahoo_finance/`, `plugins/scholar/`

**Novos caminhos propostos:** `src/kdrx/research/structured_data.py`, `tests/plugins/test_data_contracts.py`

**Motivação:** Dados estruturados precisam preservar unidade, período, revisão e fonte; descrição de plugin não é evidência de dado obtido.

**Achados relacionados:** F-15

#### Subtarefas

- [ ] **KS-047.1** Implementar adaptadores independentes quando necessário, usando documentação e acessos autorizados de cada fonte.

- [ ] **KS-047.2** Normalizar identificador de série/empresa/obra, moeda, unidade, frequência, geografia, período e timestamp de consulta.

- [ ] **KS-047.3** Distinguir missing, zero, estimativa, revisão e erro de provedor; nunca substituir ausência por zero silenciosamente.

- [ ] **KS-047.4** Guardar resposta original e transformação aplicada; cálculo subsequente recebe dataset versionado.

- [ ] **KS-047.5** Adicionar validações cruzadas de escala, datas e identidade, evitando misturar valores nominais/reais ou períodos incompatíveis.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-047-1** (`test_ks_047_1`): Valor ausente continua ausente e não altera uma média como se fosse zero.

- **AT-047-2** (`test_ks_047_2`): Tabela final permite recuperar a observação exata do provedor e sua unidade/período.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-048 — Implementar pesquisa em lote por itens e campos

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Retrieval + integrações

**Depende de:** KS-029, KS-032, KS-039, KS-047

**Correspondência com roadmap anterior:** SW-07, SW-08

**Arquivos atuais afetados:** `src/kdrx/schemas/request.py`, `src/kdrx/runner.py`, `docs/`

**Novos caminhos propostos:** `src/kdrx/research/batch.py`, `src/kdrx/schemas/batch.py`, `tests/research/test_batch.py`

**Motivação:** Paridade útil com swarm inclui tarefas amplas e repetitivas, não apenas um relatório textual sobre um corpus.

#### Subtarefas

- [ ] **KS-048.1** Adicionar schema items/fields com tipo esperado, criticidade, fonte preferida e regra para dados ausentes por célula.

- [ ] **KS-048.2** Decompor em shards com deduplicação de buscas por entidade e cache compartilhado autorizado.

- [ ] **KS-048.3** Persistir estado por célula/campo e permitir retomar apenas os campos pendentes ou invalidados.

- [ ] **KS-048.4** Verificar cada valor contra evidência exata e exportar referências por célula, não apenas bibliografia global.

- [ ] **KS-048.5** Controlar distribuição de orçamento para que entidades iniciais não consumam todo o limite e deixem o restante silenciosamente vazio.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-048-1** (`test_ks_048_1`): Pesquisa de cem entidades retoma apenas as células faltantes após interrupção.

- **AT-048-2** (`test_ks_048_2`): Cada valor numérico exportado possui unidade, período e evidência rastreável ou estado explícito de ausência.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


## D — Evidência e raciocínio verificável


### KS-049 — Decompor claims semanticamente em português e inglês

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-014, KS-041, KS-044

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/claims.py`, `src/kdrx/schemas/claims.py`

**Novos caminhos propostos:** `src/kdrx/research/claim_extraction.py`, `tests/epistemics/test_atomic_claims.py`

**Motivação:** O decomposer atual usa conjunções e verbos de uma lista inglesa; isso não cobre causalidade, negação, comparação ou idiomas adequadamente.

**Achados relacionados:** F-07, F-09

#### Subtarefas

- [ ] **KS-049.1** Extrair sujeito, predicado, objeto, polaridade, quantidade, modalidade e escopo com modelo estruturado validado.

- [ ] **KS-049.2** Preservar qualificadores compartilhados na divisão de frases; não transformar associação em causalidade.

- [ ] **KS-049.3** Gerar IDs estáveis por conteúdo normalizado+scope+source revision e manter vínculo com frase original.

- [ ] **KS-049.4** Diferenciar fato, inferência, recomendação, opinião e hipótese; exigir evidência segundo a classe e criticidade.

- [ ] **KS-049.5** Manter heurística atual como fallback rotulado e testar casos multilíngues anotados independentemente.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-049-1** (`test_ks_049_1`): Frase com and/e e escopo compartilhado produz claims que não perdem população ou condição.

- **AT-049-2** (`test_ks_049_2`): Uma negação permanece negada após extração e resumo.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-050 — Verificar entailment sem usar vocabulário como prova

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-006, KS-014, KS-049

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/claims.py`, `src/kdrx/reporting.py`

**Novos caminhos propostos:** `src/kdrx/research/semantic_verifier.py`, `tests/epistemics/test_entailment.py`

**Motivação:** entailment_score mede overlap lexical e números; frase negada pode conter todas as palavras da claim positiva.

**Achados relacionados:** F-07, F-09

#### Subtarefas

- [ ] **KS-050.1** Criar verificador independente com classes supports/contradicts/partial/context/insufficient e referência ao trecho exato.

- [ ] **KS-050.2** Combinar verificações determinísticas de números/identidade com NLI ou LLM calibrado; não depender de um único score agregado.

- [ ] **KS-050.3** Exigir justificativa curta baseada na evidência, sem solicitar ou armazenar raciocínio privado do modelo.

- [ ] **KS-050.4** Calibrar thresholds e abstenção em hard negatives com negação, entidades trocadas, causalidade e quantificadores.

- [ ] **KS-050.5** Manter lexical_score como diagnóstico de retrieval; impedir que sozinho promova claim crítica a verificada.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-050-1** (`test_ks_050_1`): The treatment is effective versus The treatment is not effective não recebe suporte positivo.

- **AT-050-2** (`test_ks_050_2`): Frase parecida sobre outra entidade é rejeitada apesar de alto overlap.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-051 — Verificar números, unidades e comparações reproduzivelmente

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-049, KS-050

**Correspondência com roadmap anterior:** SW-11, SW-12

**Arquivos atuais afetados:** `src/kdrx/claims.py`, `src/kdrx/verification.py`, `src/kdrx/reporting.py`

**Novos caminhos propostos:** `src/kdrx/research/numeric_verifier.py`, `tests/epistemics/test_numbers.py`

**Motivação:** Concordância de tokens numéricos não detecta unidade, denominador, percentagem relativa ou escala incompatível.

**Achados relacionados:** F-09, F-14

#### Subtarefas

- [ ] **KS-051.1** Representar Quantity com valor, intervalo, unidade, denominador, período, moeda e precisão.

- [ ] **KS-051.2** Implementar conversões autorizadas e tolerâncias explícitas; diferenciar pontos percentuais de variação percentual.

- [ ] **KS-051.3** Extrair valor e cabeçalho da mesma tabela/bloco e manter vínculo com dataset/cálculo.

- [ ] **KS-051.4** Comparar baseline e tratamento sob mesmo protocolo; claims de superioridade exigem condições comparáveis.

- [ ] **KS-051.5** Bloquear números novos sem lineage e classificar arredondamento aceitável versus alteração material.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-051-1** (`test_ks_051_1`): 5 ms não é tratado como 5 s e 10% relativo não é confundido com 10 pontos percentuais.

- **AT-051-2** (`test_ks_051_2`): Número arredondado dentro da tolerância passa; mudança de denominador não passa.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-052 — Separar tempo do fato, publicação e observação

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-037, KS-049

**Correspondência com roadmap anterior:** SW-11, SW-15

**Arquivos atuais afetados:** `src/kdrx/claims.py`, `src/kdrx/schemas/claims.py`, `src/kdrx/schemas/corpus.py`

**Novos caminhos propostos:** `tests/epistemics/test_scope_and_time.py`

**Motivação:** compute_temporal_match compara escopo com ano de publicação, embora uma fonte posterior possa descrever fatos anteriores.

**Achados relacionados:** F-09

#### Subtarefas

- [ ] **KS-052.1** Definir event_time, publication_time, valid_from/valid_to e retrieved_at como conceitos distintos.

- [ ] **KS-052.2** Comparar entidade, população, jurisdição, intervenção, baseline e condições relevantes da claim com a evidência.

- [ ] **KS-052.3** Permitir fonte publicada em 2026 descrever evento de 2019 quando o texto sustentar esse fato.

- [ ] **KS-052.4** Marcar incerteza temporal e precisão incompleta sem inventar datas; exigir atualização para fatos instáveis.

- [ ] **KS-052.5** Gerar relação QUALIFIES quando a evidência sustenta apenas um escopo menor, preservando a ressalva no relatório.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-052-1** (`test_ks_052_1`): Fonte de 2026 sobre evento de 2019 não falha apenas por diferença de ano de publicação.

- **AT-052-2** (`test_ks_052_2`): Resultado em uma população não é generalizado para outra sem sinalização explícita.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-053 — Avaliar qualidade da fonte segundo domínio e tipo de alegação

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-037, KS-050, KS-052

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/verification.py`, `src/kdrx/claims.py`, `src/kdrx/schemas/corpus.py`

**Novos caminhos propostos:** `src/kdrx/research/evidence_policy.py`, `tests/epistemics/test_source_policy.py`

**Motivação:** Identidade, extração, autoridade e suporte semântico são propriedades diferentes; um DOI real não torna toda frase correta.

#### Subtarefas

- [ ] **KS-053.1** Separar source_exists, identity_verified, extracted, content_verified, peer_review_status e entailment_verified.

- [ ] **KS-053.2** Definir políticas por domínio: implementação oficial para comportamento de API, estudo adequado para alegação científica, documento primário para dado corporativo.

- [ ] **KS-053.3** Não elevar metadados incompletos a GOOD/EXCELLENT por padrão; registrar justificativa e quem/qual regra atribuiu a nota.

- [ ] **KS-053.4** Expor conflitos de interesse, limitações metodológicas, retratação e qualidade de acesso separadamente.

- [ ] **KS-053.5** Quando aplicável, integrar avaliação metodológica específica com revisão especializada; não usar um rótulo genérico como substituto de análise.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-053-1** (`test_ks_053_1`): Artigo existente mas não lido não produz claim marcada como semanticamente verificada.

- **AT-053-2** (`test_ks_053_2`): Fonte oficial sustenta especificação declarada, mas não prova por si só superioridade comparativa de produto.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-054 — Calcular independência de evidência, não contagem de URLs

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-040, KS-043, KS-053

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/corpus.py`, `src/kdrx/claims.py`

**Novos caminhos propostos:** `src/kdrx/research/source_dependencies.py`, `tests/epistemics/test_independence.py`

**Motivação:** independence_families funciona sobre dependencies fornecidas, mas descoberta e validação dessas relações precisam integrar o fluxo.

#### Subtarefas

- [ ] **KS-054.1** Detectar obra original, comunicado de imprensa, dataset comum, republicação, tradução e citações secundárias.

- [ ] **KS-054.2** Criar relações de dependência com grau de certeza, evidência e proveniência; não assumir que domínios diferentes são independentes.

- [ ] **KS-054.3** Propagar famílias de origem por fecho transitivo e calcular suporte independente por claim, não apenas por corpus.

- [ ] **KS-054.4** Evitar fundir fontes independentes apenas porque tratam da mesma entidade ou repetem um fato conhecido.

- [ ] **KS-054.5** Testar se votos adicionais de agentes usando a mesma fonte mudam indevidamente a confiança; bloquear esse efeito.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-054-1** (`test_ks_054_1`): Cinco matérias derivadas do mesmo release contam como uma família de evidência para a alegação original.

- **AT-054-2** (`test_ks_054_2`): Dois estudos realmente independentes não colapsam por títulos semelhantes.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-055 — Pesquisar contraevidência dirigida por risco

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-016, KS-044, KS-050, KS-052, KS-054

**Correspondência com roadmap anterior:** SW-08, SW-11

**Arquivos atuais afetados:** `src/kdrx/verification.py`, `plugins/kdr-x/agents/counterevidence-researcher.md`

**Novos caminhos propostos:** `src/kdrx/research/falsification.py`, `tests/epistemics/test_falsification.py`

**Motivação:** Falsificação útil precisa procurar condições em que uma conclusão falha, não apenas pedir discordância retórica a outro agente.

**Achados relacionados:** F-08

#### Subtarefas

- [ ] **KS-055.1** Priorizar claims críticas, causais, surpreendentes ou com uma única família de suporte.

- [ ] **KS-055.2** Gerar queries para resultados negativos, correções, baseline alternativo, população diferente e condições-limite.

- [ ] **KS-055.3** Solicitar avaliação independente antes de mostrar a conclusão do autor quando o desenho do teste permitir.

- [ ] **KS-055.4** Converter evidência encontrada em relações verificadas e atualização de standing; medir rendimento por consulta.

- [ ] **KS-055.5** Encerrar busca adversarial por orçamento ou saturação e registrar que ausência de contraevidência não é prova de verdade.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-055-1** (`test_ks_055_1`): Contraexemplo válido força revisão da conclusão ou restrição de escopo.

- **AT-055-2** (`test_ks_055_2`): Um agente discordante sem evidência não ganha peso apenas por ocupar papel de devil’s advocate.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-056 — Calibrar confiança e distinguir desconhecido de falso

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-050, KS-051, KS-053, KS-054, KS-055

**Correspondência com roadmap anterior:** SW-11

**Arquivos atuais afetados:** `src/kdrx/claims.py`, `src/kdrx/evals.py`

**Novos caminhos propostos:** `src/kdrx/research/calibration.py`, `tests/epistemics/test_calibration.py`

**Motivação:** Uma combinação transparente de pesos ainda precisa ser calibrada para representar confiabilidade real.

**Achados relacionados:** F-09

#### Subtarefas

- [ ] **KS-056.1** Preservar estados supported, contradicted, mixed, insufficient e unavailable; erro de ferramenta não equivale a refutação.

- [ ] **KS-056.2** Calibrar probabilidades somente contra rótulos independentes e exibir incerteza quando o conjunto de calibração não cobre o domínio.

- [ ] **KS-056.3** Medir Brier score/ECE e risco seletivo, não usar uma métrica chamada calibration sem verificar o que ela calcula.

- [ ] **KS-056.4** Registrar versão de pesos, modelo verificador, conjunto de calibração e policy em cada standing.

- [ ] **KS-056.5** Permitir abstenção e ressalva em vez de forçar um consenso; não interpretar média de opiniões como evidência independente.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-056-1** (`test_ks_056_1`): Timeout de leitura gera unavailable/unverified, não false.

- **AT-056-2** (`test_ks_056_2`): Confiança declarada mantém erro observado compatível no heldout ou o gate reprova a calibração.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-057 — Cobrir todas as afirmações materiais do texto final

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-011, KS-013, KS-049, KS-050, KS-051, KS-056

**Correspondência com roadmap anterior:** SW-11, SW-12

**Arquivos atuais afetados:** `src/kdrx/reporting.py`, `src/kdrx/cli.py`

**Novos caminhos propostos:** `src/kdrx/delivery/claim_coverage.py`, `tests/epistemics/test_report_coverage.py`

**Motivação:** O gate atual procura statements registrados por substring e detector quantitativo; afirmação nova não numérica pode escapar.

**Achados relacionados:** F-06, F-10

#### Subtarefas

- [ ] **KS-057.1** Extrair claims novamente do texto final e compará-las com o registry, inclusive paráfrases e alegações sem números.

- [ ] **KS-057.2** Exigir mapeamento sentença/trecho de relatório -> claim -> evidence edge -> snapshot; registrar recomendações e inferências como tais.

- [ ] **KS-057.3** Detectar omissão de material crítico sem exigir inclusão de toda frase irrelevante extraída do corpus.

- [ ] **KS-057.4** Validar referência junto à alegação sustentada, não apenas presença de fonte em algum lugar do documento.

- [ ] **KS-057.5** Bloquear falsidade ou suporte insuficiente segundo criticidade e permitir linguagem inconclusiva vinculada a lacunas explícitas.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-057-1** (`test_ks_057_1`): Frase inventada sem números adicionada ao relatório não passa despercebida.

- **AT-057-2** (`test_ks_057_2`): Paráfrase fiel passa sem exigir cópia literal da statement registrada.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-058 — Propagar alterações de evidência até as entregas

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Engenharia de evidência + avaliação

**Depende de:** KS-020, KS-032, KS-040, KS-056, KS-057

**Correspondência com roadmap anterior:** SW-15

**Arquivos atuais afetados:** `src/kdrx/claims.py`, `src/kdrx/verification.py`, `src/kdrx/reporting.py`

**Novos caminhos propostos:** `src/kdrx/research/impact_graph.py`, `tests/epistemics/test_invalidation.py`

**Motivação:** Retratações e mudanças de fonte precisam invalidar apenas as conclusões realmente dependentes.

#### Subtarefas

- [ ] **KS-058.1** Persistir DAG de dependências source revision -> span -> claim/edge -> cálculo -> seção -> delivery.

- [ ] **KS-058.2** Aplicar eventos de correção/retratação como novas revisões com timestamp e escopo.

- [ ] **KS-058.3** Recalcular claims afetadas, invalidar seções e sinalizar entregas históricas impactadas sem apagar a versão anterior.

- [ ] **KS-058.4** Preservar claims com suporte independente suficiente e registrar por que permaneceram válidas.

- [ ] **KS-058.5** Tornar atualização transacional e retomável; não deixar metade do grafo com standing novo e metade com antigo.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-058-1** (`test_ks_058_1`): Retratação de uma fonte modifica somente claims e relatórios dependentes.

- **AT-058-2** (`test_ks_058_2`): Interrupção durante atualização é reconciliada sem misturar revisões de standing.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


## E — Relatórios, cálculos e artefatos


### KS-059 — Planejar relatório por requisitos e evidência

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Síntese + artefatos

**Depende de:** KS-024, KS-049, KS-056

**Correspondência com roadmap anterior:** SW-12

**Arquivos atuais afetados:** `src/kdrx/reporting.py`, `plugins/kdr-x/agents/writing.md`

**Novos caminhos propostos:** `src/kdrx/delivery/outline.py`, `tests/delivery/test_outline.py`

**Motivação:** O report swarm Python é determinístico; temas incluem heurísticas como palavra mais longa, não uma equipe editorial real.

**Achados relacionados:** F-10, F-11

#### Subtarefas

- [ ] **KS-059.1** Criar OutlineSpec com objetivos de seção, perguntas respondidas, claims elegíveis, lacunas e critérios de aceite.

- [ ] **KS-059.2** Usar council apenas quando a complexidade justificar e registrar decisões; relatório curto não precisa de cinco planejadores.

- [ ] **KS-059.3** Resolver dependências entre seções e escrever síntese executiva após o corpo aprovado.

- [ ] **KS-059.4** Construir EvidencePack mínimo por seção com fontes/spans autorizados e proibições de extrapolação.

- [ ] **KS-059.5** Verificar cobertura do pedido e redundância antes de gastar com escritores.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-059-1** (`test_ks_059_1`): Toda seção tem finalidade vinculada a requisito e evidência disponível.

- **AT-059-2** (`test_ks_059_2`): Conselho não cria capítulos preenchidos com prosa apenas para aumentar tamanho do relatório.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-060 — Executar writers, reviewers e fixers reais

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Síntese + artefatos

**Depende de:** KS-025, KS-027, KS-029, KS-031, KS-059

**Correspondência com roadmap anterior:** SW-12

**Arquivos atuais afetados:** `src/kdrx/reporting.py`, `plugins/kdr-x/agents/writing.md`, `plugins/kdr-x/agents/reviewer.md`

**Novos caminhos propostos:** `src/kdrx/delivery/editorial_pipeline.py`, `tests/live/test_editorial_pipeline.py`

**Motivação:** Classes de papéis determinísticos não equivalem a agentes independentes com revisão observada.

**Achados relacionados:** F-10, F-11

#### Subtarefas

- [ ] **KS-060.1** Disparar tarefas de escrita por seção usando backend real, EvidencePack e quota específicos.

- [ ] **KS-060.2** Agendar revisão independente com checks semânticos e mecânicos; escritor não controla o resultado da revisão.

- [ ] **KS-060.3** Aplicar repair focado em defects estruturados com limite de tentativas e sem reescrever evidência ou rubric.

- [ ] **KS-060.4** Persistir cada versão de seção e seus pareceres para resume granular.

- [ ] **KS-060.5** Controlar consistência entre seções por editor de termos/transições sem permitir introdução de fatos novos não verificados.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-060-1** (`test_ks_060_1`): Trace mostra identidades distintas de writer/reviewer e defeitos que realmente provocaram correção.

- **AT-060-2** (`test_ks_060_2`): Falha de uma seção não obriga a reescrever todas as seções já aprovadas.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-061 — Montar relatório mecanicamente a partir de IR validada

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Síntese + artefatos

**Depende de:** KS-013, KS-057, KS-059, KS-060

**Correspondência com roadmap anterior:** SW-12

**Arquivos atuais afetados:** `src/kdrx/reporting.py`

**Novos caminhos propostos:** `src/kdrx/delivery/report_ir.py`, `src/kdrx/delivery/assembler.py`, `tests/delivery/test_assembly.py`

**Motivação:** Montagem final precisa preservar vínculos de evidência e não depender de regex sobre prosa livre para reconstruí-los.

**Achados relacionados:** F-06, F-10

#### Subtarefas

- [ ] **KS-061.1** Definir ReportIR com seções, frases materiais, citações tipadas, tabelas, figuras, notas de incerteza e requisitos atendidos.

- [ ] **KS-061.2** Combinar seções por IDs e ordem aprovada, rejeitando refs inexistentes, duplicadas ou contraditórias.

- [ ] **KS-061.3** Gerar bibliografia apenas das fontes realmente citadas e validar citação local junto à frase correspondente.

- [ ] **KS-061.4** Produzir Markdown/HTML de maneira determinística, preservando IDs e link de proveniência.

- [ ] **KS-061.5** Reexecutar verificação de claims/números sobre a versão renderizada, porque transformação de formatação também pode alterar significado.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-061-1** (`test_ks_061_1`): Montagens repetidas da mesma IR produzem bytes idênticos para o mesmo renderer/version.

- **AT-061-2** (`test_ks_061_2`): Uma seção aponta para fonte inexistente: assembly falha antes da publicação.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-062 — Adicionar certificado de entrega verificável por consumidor

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Síntese + artefatos

**Depende de:** KS-012, KS-022, KS-057, KS-061

**Correspondência com roadmap anterior:** SW-03, SW-12

**Arquivos atuais afetados:** `src/kdrx/cli.py`, `src/kdrx/schemas/artifact.py`, `src/kdrx/native_hooks.py`

**Novos caminhos propostos:** `src/kdrx/delivery/certificate.py`, `tests/delivery/test_certificate.py`

**Motivação:** O diferencial proposto é permitir verificar uma entrega e sua proveniência sem confiar no agente que a redigiu.

**Achados relacionados:** F-04, F-10

#### Subtarefas

- [ ] **KS-062.1** Emitir DeliveryCertificate com report_hash, artifact hashes, graph revision, gate decisions, policy version, limitações e status deliverable.

- [ ] **KS-062.2** Adicionar comando verify-delivery offline que confira blobs, refs e política aplicada, sem chamar LLM.

- [ ] **KS-062.3** Assinar certificados quando houver distribuição externa e política de chaves definida; hash sozinho prova integridade, não identidade do emissor.

- [ ] **KS-062.4** Distinguir evidência de execução e julgamento semântico: certificado registra ambos sem prometer prova matemática da verdade.

- [ ] **KS-062.5** Incluir suporte a invalidação/revogação e vínculo com entregas substitutas quando houver correção de fonte.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-062-1** (`test_ks_062_1`): Consumidor detecta alteração de um byte e consegue localizar a referência quebrada.

- **AT-062-2** (`test_ks_062_2`): Certificado sem evidência ou com política antiga não é interpretado como aprovação universal.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-063 — Corrigir reprodução de cálculos por conteúdo real

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Síntese + artefatos

**Depende de:** KS-022, KS-031, KS-047, KS-051

**Correspondência com roadmap anterior:** SW-11, SW-12

**Arquivos atuais afetados:** `src/kdrx/analysis.py`, `src/kdrx/artifact.py`

**Novos caminhos propostos:** `src/kdrx/compute/runner.py`, `src/kdrx/compute/ledger.py`, `tests/compute/test_reproduction.py`

**Motivação:** Calculation.inputs contém hashes, mas reproducible_from chama runner(self.inputs); conteúdo, script e unit_checks não são executados por esse contrato.

**Achados relacionados:** F-14

#### Subtarefas

- [ ] **KS-063.1** Resolver cada input hash para blob e verificar seu conteúdo antes de entregar dados ao runner.

- [ ] **KS-063.2** Persistir script/version/hash, ambiente lockado, parâmetros, seeds e bibliotecas necessárias.

- [ ] **KS-063.3** Executar script em sandbox sem rede por padrão, com limites de recursos e outputs autorizados.

- [ ] **KS-063.4** Transformar unit_checks em testes executáveis observados pelo kernel; strings declaradas não são provas de execução.

- [ ] **KS-063.5** Comparar outputs exatos quando determinísticos ou tolerâncias numéricas pré-definidas quando justificadas; vincular tabelas/figuras ao cálculo.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-063-1** (`test_ks_063_1`): Runner recebe os valores originais, e não strings de SHA-256, e reproduz o resultado registrado.

- **AT-063-2** (`test_ks_063_2`): Alterar input, script, unidade ou ambiente invalida a reprodução ou exige nova versão.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-064 — Entregar documentos e mídia com verificação de abertura

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Síntese + artefatos

**Depende de:** KS-041, KS-046, KS-048, KS-061, KS-062, KS-063

**Correspondência com roadmap anterior:** SW-12

**Arquivos atuais afetados:** `src/kdrx/artifact.py`, `src/kdrx/reporting.py`

**Novos caminhos propostos:** `src/kdrx/delivery/exporters/`, `tests/delivery/test_exporters.py`

**Motivação:** Equivalência ampla ao Kimi exige artefatos utilizáveis; read_bytes sem erro não verifica renderização nem abertura em formato de destino.

#### Subtarefas

- [ ] **KS-064.1** Implementar exporters por capacidade: Markdown/HTML primeiro e PDF/DOCX/XLSX/PPTX conforme escopo liberado.

- [ ] **KS-064.2** Fixar renderer/version/fontes licenciadas e políticas de metadados; não forjar autoria, assinatura ou validação externa.

- [ ] **KS-064.3** Validar estrutura do arquivo e abrir/renderizar amostra de páginas/abas/slides com ferramenta adequada em teste.

- [ ] **KS-064.4** Conferir que números, referências, fórmulas e textos não foram cortados ou alterados na exportação.

- [ ] **KS-064.5** Vincular cada export ao mesmo ReportIR e registrar divergências de paginação, formatos não suportados e hashes finais.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-064-1** (`test_ks_064_1`): Arquivo com extensão correta mas bytes inválidos falha no teste de abertura.

- **AT-064-2** (`test_ks_064_2`): Tabela exportada mantém valores/unidades/citações da IR sem perda silenciosa.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


## F — Inteligência adaptativa


### KS-065 — Construir ContextPacks mínimos e compactação auditável

**Prioridade:** P2 · **Estado:** proposta, não implementada · **Responsável sugerido:** Orquestração adaptativa

**Depende de:** KS-024, KS-029, KS-040, KS-056

**Correspondência com roadmap anterior:** SW-10

**Arquivos atuais afetados:** `src/kdrx/schemas/plan.py`, `src/kdrx/reporting.py`

**Novos caminhos propostos:** `src/kdrx/runtime/context.py`, `tests/runtime/test_context.py`

**Motivação:** Contexto amplo e compartilhado sem controle aumenta custo e contamina independência de verificadores.

#### Subtarefas

- [ ] **KS-065.1** Criar ContextPack por tarefa com objetivo, restrições, upstream artifact refs, trechos necessários e lacunas relevantes.

- [ ] **KS-065.2** Preservar invariantes e evidence IDs em toda compactação; não substituir fonte por resumo não rastreável.

- [ ] **KS-065.3** Aplicar limite de tokens por papel e recuperar detalhes sob demanda via broker.

- [ ] **KS-065.4** Agrupar chamadas com prefixos compatíveis apenas quando não prejudicar isolamento ou independência; medir cache real do provedor.

- [ ] **KS-065.5** Testar perda de informação em cadeias longas e contaminação por memória de outro run.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-065-1** (`test_ks_065_1`): ContextPack permite executar a tarefa sem depender de mensagens ocultas de irmãos.

- **AT-065-2** (`test_ks_065_2`): Compactação mantém ressalvas, números e refs críticas ou é rejeitada.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-066 — Escolher arquitetura e número de agentes por tarefa

**Prioridade:** P2 · **Estado:** proposta, não implementada · **Responsável sugerido:** Orquestração adaptativa

**Depende de:** KS-006, KS-027, KS-029, KS-034, KS-065

**Correspondência com roadmap anterior:** SW-07

**Arquivos atuais afetados:** `src/kdrx/runner.py`, `src/kdrx/planner.py`

**Novos caminhos propostos:** `src/kdrx/planning/router.py`, `tests/planning/test_router.py`

**Motivação:** Mais agentes é uma escolha de recursos, não uma definição de qualidade.

#### Subtarefas

- [ ] **KS-066.1** Extrair atributos de paralelizabilidade, sequencialidade, amplitude, incerteza, tool density e valor do resultado.

- [ ] **KS-066.2** Comparar rotas single-agent, fan-out independente, coordenação central e híbrida contra baseline com orçamento pareado.

- [ ] **KS-066.3** Aprender política inicialmente com regras e dados de avaliação; não introduzir RL antes de existir sinal de qualidade confiável.

- [ ] **KS-066.4** Escolher modelos/esforço por papel sob capability constraints e permitir escalada seletiva.

- [ ] **KS-066.5** Registrar decisão, alternativas e previsão de ganho; usar ablation para remover complexidade sem benefício.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-066-1** (`test_ks_066_1`): Tarefa estritamente sequencial não recebe fan-out caro sem razão.

- **AT-066-2** (`test_ks_066_2`): Mesmo budget total produz escolha mensuravelmente útil ou o router retorna ao baseline.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-067 — Replanejar a partir de lacunas e conflitos reais

**Prioridade:** P2 · **Estado:** proposta, não implementada · **Responsável sugerido:** Orquestração adaptativa

**Depende de:** KS-015, KS-032, KS-055, KS-058, KS-066

**Correspondência com roadmap anterior:** SW-08

**Arquivos atuais afetados:** `src/kdrx/planner.py`, `src/kdrx/retrieval.py`

**Novos caminhos propostos:** `src/kdrx/planning/replanner.py`, `tests/planning/test_replanning.py`

**Motivação:** O swarm desejado deve adaptar trabalho ao que descobriu, sem perder controle sobre a execução.

**Achados relacionados:** F-08

#### Subtarefas

- [ ] **KS-067.1** Assinar eventos de gap/contradiction e gerar PlanPatch específico em vez de reiniciar o plano inteiro.

- [ ] **KS-067.2** Adicionar tarefa somente quando houver hipótese de ganho informacional e orçamento reservado.

- [ ] **KS-067.3** Separar necessidade de mais fontes, verificação de fonte existente, cálculo e esclarecimento de requisito.

- [ ] **KS-067.4** Reusar evidência válida por hash e invalidar somente os nós realmente afetados.

- [ ] **KS-067.5** Limitar profundidade, revisões e tentativas de reparo; exceder limite produz diagnóstico e entrega parcial explicitamente rotulada.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-067-1** (`test_ks_067_1`): Nova contradição dispara verificação direcionada, não outro ciclo completo indiferenciado.

- **AT-067-2** (`test_ks_067_2`): Planos sucessivos não recriam a mesma tarefa sob IDs diferentes para contornar budget.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-068 — Parar por ganho marginal e risco residual

**Prioridade:** P2 · **Estado:** proposta, não implementada · **Responsável sugerido:** Orquestração adaptativa

**Depende de:** KS-015, KS-029, KS-055, KS-056, KS-067

**Correspondência com roadmap anterior:** SW-08

**Arquivos atuais afetados:** `src/kdrx/retrieval.py`, `src/kdrx/scheduler.py`

**Novos caminhos propostos:** `src/kdrx/planning/stopping.py`, `tests/planning/test_stopping.py`

**Motivação:** No-progress precisa medir novidade e resolução, não apenas capturar exceções ou contar pesquisas.

**Achados relacionados:** F-08

#### Subtarefas

- [ ] **KS-068.1** Medir novas famílias de fontes, requisitos resolvidos, redução de incerteza e conflitos encerrados por rodada.

- [ ] **KS-068.2** Normalizar ganho pelo custo/latência e distinguir repetição lexical de evidência realmente nova.

- [ ] **KS-068.3** Usar janelas de saturação configuradas em dev e prever ganho esperado de mais uma chamada.

- [ ] **KS-068.4** Manter prioridade de claims críticas abertas e aplicar orçamento global independentemente da pressão por completar relatório.

- [ ] **KS-068.5** Emitir reason_code de parada e o que seria necessário para resolver o restante.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-068-1** (`test_ks_068_1`): Repetição de fontes já conhecidas aciona parada sem contar como progresso.

- **AT-068-2** (`test_ks_068_2`): Uma fonte nova mas irrelevante não prolonga indefinidamente a execução.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-069 — Adicionar memória governada sem contaminar avaliações

**Prioridade:** P2 · **Estado:** proposta, não implementada · **Responsável sugerido:** Orquestração adaptativa

**Depende de:** KS-020, KS-040, KS-058, KS-065

**Correspondência com roadmap anterior:** SW-10, SW-15

**Arquivos atuais afetados:** `src/kdrx/artifact.py`, `src/kdrx/state.py`

**Novos caminhos propostos:** `src/kdrx/memory/store.py`, `tests/security/test_memory_scope.py`

**Motivação:** Aprendizado contínuo precisa separar experiência operacional de fatos que expiram e de dados privados.

#### Subtarefas

- [ ] **KS-069.1** Separar memória run/project/user e políticas de retenção, consentimento e exclusão.

- [ ] **KS-069.2** Armazenar receitas de tarefas e erros resolvidos com proveniência, sem guardar raciocínio privado ou segredos.

- [ ] **KS-069.3** Revalidar fatos temporais antes de reutilização; memória antiga não substitui consulta a fonte necessária.

- [ ] **KS-069.4** Isolar conjuntos de benchmark e proibir que respostas heldout entrem em memória usada pelos concorrentes.

- [ ] **KS-069.5** Promover alterações de prompts/skills por PR, avaliação e canário; impedir autoedição privilegiada durante um run.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-069-1** (`test_ks_069_1`): Memória de outro projeto/usuário não aparece no ContextPack.

- **AT-069-2** (`test_ks_069_2`): Um fato expirado é revalidado e uma skill ruim pode ser revertida sem reescrever histórico.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-070 — Transformar monitoramento local em pesquisa incremental controlada

**Prioridade:** P2 · **Estado:** proposta, não implementada · **Responsável sugerido:** Orquestração adaptativa

**Depende de:** KS-039, KS-044, KS-058, KS-068, KS-069

**Correspondência com roadmap anterior:** SW-15

**Arquivos atuais afetados:** `src/kdrx/cli.py`, `src/kdrx/retrieval.py`, `src/kdrx/reporting.py`

**Novos caminhos propostos:** `src/kdrx/monitor/service.py`, `tests/live/test_delta_research.py`

**Motivação:** Monitoramento já possui primitivas locais; atualizações web precisam de execução real, políticas e impacto rastreável.

#### Subtarefas

- [ ] **KS-070.1** Persistir standing queries com frequência, TTL, budget, fontes e autorização de execução em serviço/agendador real.

- [ ] **KS-070.2** Executar delta retrieval com ETag/Last-Modified quando disponíveis e novos snapshots para alterações.

- [ ] **KS-070.3** Classificar mudança cosmética, correção factual, fonte retirada e atualização de conteúdo.

- [ ] **KS-070.4** Propagar impacto pelo grafo e gerar diff de claims/relatório com links para evidência nova e anterior.

- [ ] **KS-070.5** Permitir pausar/cancelar monitor e limitar notificações; não anunciar automação ativa sem serviço configurado e funcionando.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-070-1** (`test_ks_070_1`): Correção de fonte atualiza apenas conclusões afetadas e produz diff verificável.

- **AT-070-2** (`test_ks_070_2`): Monitor desabilitado não faz requests nem gera custos ocultos.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


## G — Prova comparativa


### KS-071 — Criar datasets adversariais separados do código de detecção

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Avaliação independente

**Depende de:** KS-006, KS-049, KS-050, KS-051, KS-057

**Correspondência com roadmap anterior:** SW-16

**Arquivos atuais afetados:** `src/kdrx/evals.py`, `tests/test_phase9b_evals.py`

**Novos caminhos propostos:** `evals/datasets/`, `evals/annotations.schema.json`, `tests/evals/test_dataset_integrity.py`

**Motivação:** Os seeded detectors atuais conhecem URIs confiáveis e regras simples; repetição determinística não mede estabilidade de LLMs.

**Achados relacionados:** F-16

#### Subtarefas

- [ ] **KS-071.1** Criar corpus de hard negatives com fonte real que não sustenta a claim, negação, causalidade, números, escopo e independência enganosa.

- [ ] **KS-071.2** Anotar independentemente evidência correta e rubricas por requisito; separar anotadores de autores do detector.

- [ ] **KS-071.3** Usar tarefas públicas para desenvolvimento e conjunto privado recente para confirmação, com acesso controlado e hashes.

- [ ] **KS-071.4** Incluir casos PT/EN, texto+documento, código, tabelas e perguntas cuja resposta correta é insuficiência de evidência.

- [ ] **KS-071.5** Preservar golden outputs versionados e impedir alteração de rótulo para fazer patch passar sem revisão independente.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-071-1** (`test_ks_071_1`): Verificador com overlap lexical alto falha nos hard negatives até correção real.

- **AT-071-2** (`test_ks_071_2`): Conjunto privado não aparece em prompts de tuning, memória ou fixtures usadas para calibrar thresholds.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-072 — Testar propriedades, falhas e invariantes de segurança

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Avaliação independente

**Depende de:** KS-008, KS-012, KS-017, KS-021, KS-022, KS-027, KS-028, KS-031, KS-032

**Correspondência com roadmap anterior:** SW-06, SW-13, SW-17

**Arquivos atuais afetados:** `src/kdrx/dag.py`, `src/kdrx/state.py`, `tests/`

**Novos caminhos propostos:** `tests/property/`, `tests/chaos/`, `tests/security/`

**Motivação:** As invariantes importantes exigem casos gerados e interrupções reais, não apenas caminhos felizes.

**Achados relacionados:** F-02, F-16, F-18

#### Subtarefas

- [ ] **KS-072.1** Gerar DAGs válidos/inválidos, aliases de outputs e cadeias profundas; substituir recursão onde limites de profundidade forem problema.

- [ ] **KS-072.2** Injetar kill do orchestrator/worker antes e depois de cada commit, timeout, corrupção, disco cheio e eventos fora de ordem.

- [ ] **KS-072.3** Testar isolamento com symlinks/junctions, caminhos Windows, redirects, rebinding e conteúdo de ferramenta adversarial.

- [ ] **KS-072.4** Executar testes de mutação em validação de identidade, gates e hashes para provar que a suíte detecta remoção desses checks.

- [ ] **KS-072.5** Registrar invariantes como nenhuma dupla publicação, nenhum lease antigo aceito e nenhum efeito não autorizado nos cenários cobertos.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-072-1** (`test_ks_072_1`): Matar processos em todos os pontos de commit preserva estado comprometido e recupera órfãos.

- **AT-072-2** (`test_ks_072_2`): Remover deliberadamente um check crítico faz a suíte falhar, provando que o check é exercitado.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-073 — Executar testes reais do host em instalações limpas

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Avaliação independente

**Depende de:** KS-005, KS-025, KS-026, KS-030, KS-034, KS-045

**Correspondência com roadmap anterior:** SW-01, SW-16, SW-17

**Arquivos atuais afetados:** `tests/test_workflows.py`, `tests/test_plugin_selfcontained.py`, `.github/`

**Novos caminhos propostos:** `tests/live/test_clean_install.py`, `.github/workflows/live-compat.yml`

**Motivação:** Compilar AsyncFunction não demonstra que descoberta, hooks e execução funcionam no Claude Code instalado.

**Achados relacionados:** F-16

#### Subtarefas

- [ ] **KS-073.1** Instalar wheel e plugin de release em projeto vazio fora do checkout; proibir acesso implícito a ../../src.

- [ ] **KS-073.2** Validar descoberta de todos os agentes realmente registrados e paridade com role-resolution, sem herdar contagem antiga de 17.

- [ ] **KS-073.3** Executar plan/run/resume/verify/seal e uma tarefa live curta no host real por matriz de versões suportadas.

- [ ] **KS-073.4** Cobrir Linux e plataformas declaradas Windows/macOS com filesystem e PATH reais; skips não contam como suporte testado.

- [ ] **KS-073.5** Executar suite live em ambiente protegido e com teto de custo; PR de fork não recebe secrets nem poder de rodar código arbitrário com credenciais.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-073-1** (`test_ks_073_1`): Plugin instalado em diretório limpo funciona sem o monorepo presente.

- **AT-073-2** (`test_ks_073_2`): Quebra em versão do host é detectada antes da release e atualiza matriz de suporte.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-074 — Comparar contra single-agent e Kimi com condições documentadas

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Avaliação independente

**Depende de:** KS-006, KS-034, KS-048, KS-060, KS-064, KS-071, KS-073

**Correspondência com roadmap anterior:** SW-16

**Arquivos atuais afetados:** `src/kdrx/evals.py`

**Novos caminhos propostos:** `evals/runners/`, `evals/protocols/comparison_v1.json`, `evals/results/`

**Motivação:** Uma réplica de traces Kimi testa compatibilidade observacional, não equivale a executar o produto concorrente.

**Achados relacionados:** F-11, F-16

#### Subtarefas

- [ ] **KS-074.1** Rodar baseline single-agent com mesmo modelo/ferramentas e limites; rodar o baseline do commit auditado quando o tipo de tarefa for suportado.

- [ ] **KS-074.2** Executar Kimi Agent Swarm autorizado com versão/data/plano comercial e registrar limites observáveis; não chamar simples endpoint de modelo de swarm original.

- [ ] **KS-074.3** Integrar DeepResearch Bench de Du et al., versão fixada, e incluir benchmarks complementares apenas com licença/ambiente verificados.

- [ ] **KS-074.4** Separar trilha offline com snapshots congelados e trilha web viva com janela de coleta próxima entre sistemas.

- [ ] **KS-074.5** Incluir failures/timeouts/custos de todas as tentativas, não apenas runs bem-sucedidos ou melhor amostra.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-074-1** (`test_ks_074_1`): Resultados permitem reproduzir modelos, prompts, ferramentas, budgets, datas e exclusões.

- **AT-074-2** (`test_ks_074_2`): Comparação com custos internos desconhecidos do Kimi informa essa limitação em vez de inventar equivalência monetária.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-075 — Demonstrar ganho com estatística e revisão cega

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Avaliação independente

**Depende de:** KS-006, KS-071, KS-074

**Correspondência com roadmap anterior:** SW-16

**Arquivos atuais afetados:** `src/kdrx/evals.py`

**Novos caminhos propostos:** `evals/statistics.py`, `evals/human_review.md`, `tests/evals/test_statistics.py`

**Motivação:** Superioridade precisa significar ganho consistente e útil, não uma nota isolada escolhida depois do teste.

**Achados relacionados:** F-16

#### Subtarefas

- [ ] **KS-075.1** Estimar variância em piloto e determinar tamanho amostral/poder para a margem útil pré-registrada; não assumir que cem tarefas bastam.

- [ ] **KS-075.2** Executar repetições independentes onde houver estocasticidade, sem pseudorrepetir observações da mesma tarefa como tarefas diferentes.

- [ ] **KS-075.3** Usar comparação pareada por tarefa e intervalos de confiança, com tratamento de dependência e múltiplas comparações quando necessário.

- [ ] **KS-075.4** Fazer revisão humana cega em amostra estratificada de vitórias, derrotas e desacordos dos juízes; não usar apenas o mesmo modelo que escreveu.

- [ ] **KS-075.5** Publicar qualidade/factualidade, sucesso, custo por resultado correto, latência p50/p95 e abstenção; declarar domínios em que não houve ganho.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-075-1** (`test_ks_075_1`): Melhoria sem significância ou sem utilidade prática não recebe rótulo de superioridade demonstrada.

- **AT-075-2** (`test_ks_075_2`): Resultado agregado não esconde regressão grave em português, tarefas sequenciais ou claims críticas.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-076 — Otimizar e eventualmente treinar o coordenador com dados confiáveis

**Prioridade:** P2 · **Estado:** proposta, não implementada · **Responsável sugerido:** Avaliação independente

**Depende de:** KS-066, KS-067, KS-068, KS-069, KS-075

**Correspondência com roadmap anterior:** SW-07, SW-16

**Arquivos atuais afetados:** `src/kdrx/planner.py`

**Novos caminhos propostos:** `experiments/orchestration/`, `evals/ablations/`

**Motivação:** O Kimi original descreve treinamento de orquestração paralela; simplesmente acrescentar agentes não reproduz esse treinamento.

**Achados relacionados:** F-11

#### Subtarefas

- [ ] **KS-076.1** Começar com ablações de número de agentes, tipos de coordenação, roteamento de modelos, orçamento de verificação e cache.

- [ ] **KS-076.2** Coletar episódios autorizados com estados, ações de alto nível, resultados e custo; não incluir segredos nem raciocínio privado.

- [ ] **KS-076.3** Otimizar utilidade de qualidade sujeita a custo/latência/segurança, penalizando trabalho duplicado e coordenação sem contribuição.

- [ ] **KS-076.4** Se regras e bandits saturarem, avaliar treinamento supervisionado/RL do coordenador em sandbox com heldout imutável e capacidade computacional compatível.

- [ ] **KS-076.5** Promover política somente após regressão, canário e rollback; preservar baseline simples como fallback.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-076-1** (`test_ks_076_1`): Cada recurso avançado mostra ganho em ablation ou é removido/desligado.

- **AT-076-2** (`test_ks_076_2`): Reward hacking, busca de proxies ou exploração de avaliador não produz promoção para produção.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


## H — Operação, release e escala


### KS-077 — Medir execução, custo, erros e proveniência em uma trilha

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Plataforma + release

**Depende de:** KS-020, KS-021, KS-025, KS-029, KS-040

**Correspondência com roadmap anterior:** SW-14

**Arquivos atuais afetados:** `src/kdrx/state.py`, `src/kdrx/artifact.py`, `src/kdrx/cli.py`

**Novos caminhos propostos:** `src/kdrx/observability/`, `tests/observability/`

**Motivação:** Eventos locais são úteis, mas precisam correlacionar a cadeia run/task/attempt/tool/evidence/delivery.

#### Subtarefas

- [ ] **KS-077.1** Emitir spans de execução e IDs de correlação com exporter configurável, incluindo OpenTelemetry quando adotado.

- [ ] **KS-077.2** Registrar tokens/custo/latência observados, reservas, retries, queue time, caminho crítico e trabalho duplicado.

- [ ] **KS-077.3** Permitir navegar de uma claim final até tool call e snapshot de origem, com acesso restrito.

- [ ] **KS-077.4** Redigir segredos, dados privados e URLs assinadas; não capturar raciocínio privado do modelo como requisito de observabilidade.

- [ ] **KS-077.5** Adicionar replay de eventos que reconstrói estado sem nova chamada de modelo; tratar reexecução live como operação distinta e custosa.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-077-1** (`test_ks_077_1`): Uma falha em tool call pode ser correlacionada à task e às claims afetadas.

- **AT-077-2** (`test_ks_077_2`): Replay não faz rede e reconstrói o mesmo estado comprometido sem expor credenciais.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-078 — Publicar wheel/plugin reproduzíveis com supply chain verificável

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Plataforma + release

**Depende de:** KS-004, KS-045, KS-046, KS-072, KS-073

**Correspondência com roadmap anterior:** SW-01, SW-17

**Arquivos atuais afetados:** `pyproject.toml`, `.github/`, `scripts/`, `LICENSE`

**Novos caminhos propostos:** `docs/RELEASE_CHECKLIST.md`, `tests/release/`, `constraints/`

**Motivação:** Build e release precisam provar o que entregam, incluindo dependências opcionais e direitos dos componentes.

**Achados relacionados:** F-15

#### Subtarefas

- [ ] **KS-078.1** Fixar versões/hashes de dependências por ambiente de build e atualizar actions com revisão e pin de SHA; não seguir latest em produção.

- [ ] **KS-078.2** Gerar SBOM, inventário de licenças, checksums e proveniência dos pacotes produzidos.

- [ ] **KS-078.3** Comparar build em ambientes limpos e documentar fontes legítimas de não determinismo; testar instalação a partir dos artefatos, não apenas editable.

- [ ] **KS-078.4** Executar type checks, lint, cobertura de branches crítica, secret scanning e dependency audit como gates obrigatórios.

- [ ] **KS-078.5** Assinar releases quando houver política de chaves, preservar artefatos anteriores e testar downgrade/rollback de aplicação com migrações compatíveis.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-078-1** (`test_ks_078_1`): Wheel/plugin testado tem o mesmo hash do publicado e não contém componentes excluídos.

- **AT-078-2** (`test_ks_078_2`): Falha em gate obrigatório impede release mesmo se documentação declara plano concluído.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-079 — Gerar documentação de estado real e governança consistente

**Prioridade:** P1 · **Estado:** proposta, não implementada · **Responsável sugerido:** Plataforma + release

**Depende de:** KS-001, KS-005, KS-011, KS-034, KS-073, KS-077, KS-078

**Correspondência com roadmap anterior:** SW-00, SW-01, SW-17

**Arquivos atuais afetados:** `README.md`, `auditoria/`, `docs/`, `.github/`

**Novos caminhos propostos:** `docs/OPERATIONS.md`, `docs/COMPATIBILITY.md`, `scripts/generate_status.py`

**Motivação:** README, scorecards antigos e roadmap SW descrevem ciclos diferentes; o usuário precisa saber exatamente o que está liberado.

**Achados relacionados:** F-17

#### Subtarefas

- [ ] **KS-079.1** Substituir checklist global concluído por matriz capability x backend x evidência x SHA x data.

- [ ] **KS-079.2** Distinguir auditorias históricas arquivadas de estado atual, sem apagar as primeiras ou reutilizar suas notas como benchmark presente.

- [ ] **KS-079.3** Gerar contagem de testes e status de releases a partir de resultados, incluindo skips e compatibilidade não testada.

- [ ] **KS-079.4** Documentar instalação, credenciais, limites, retomada, cancelamento, backups, atualização, incidentes e política de dados.

- [ ] **KS-079.5** Verificar proteções de branch/rulesets via API apropriada e armazenar evidência; não inferir enforce_admins apenas de protected=true.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-079-1** (`test_ks_079_1`): README muda automaticamente quando teste/capacidade é removido ou não tem evidência válida.

- **AT-079-2** (`test_ks_079_2`): Guia de recuperação reproduz restauração em ambiente limpo e não depende de conhecimento tácito do autor.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


### KS-080 — Escalar para múltiplos hosts apenas após demonstrar necessidade

**Prioridade:** P3 · **Estado:** proposta, não implementada · **Responsável sugerido:** Plataforma + release

**Depende de:** KS-021, KS-022, KS-027, KS-029, KS-031, KS-033, KS-072, KS-075, KS-077, KS-078

**Correspondência com roadmap anterior:** SW-18

**Arquivos atuais afetados:** nenhum arquivo do baseline; depende de módulos criados antes

**Novos caminhos propostos:** `deploy/`, `src/kdrx/runtime/backends/distributed/`, `tests/load/`

**Motivação:** O limite local do workflow não deve ser contornado informalmente; escala distribuída traz requisitos próprios de isolamento e consistência.

#### Subtarefas

- [ ] **KS-080.1** Medir gargalo real e definir alvo de runs/workers/latência/custo antes de introduzir Postgres, fila ou object store remoto.

- [ ] **KS-080.2** Reusar portas do kernel com store transacional distribuído e blobs externos; manter contrato de lease/fencing/idempotência.

- [ ] **KS-080.3** Executar workers isolados em múltiplos hosts e aplicar quotas por usuário/projeto; tenancy só entra quando for requisito do produto.

- [ ] **KS-080.4** Testar partição de rede, duplicação de entrega, worker lento, rolling upgrade e compatibilidade de versões.

- [ ] **KS-080.5** Aumentar concorrência gradualmente e comparar fronteira qualidade/custo/latência; centenas de workers não autorizam promessa de melhor inteligência.

#### Cenários obrigatórios de aceite — a implementar e executar

- **AT-080-1** (`test_ks_080_1`): Carga acima do host único mantém invariantes e não vaza dados entre runs/tenants.

- **AT-080-2** (`test_ks_080_2`): Rollback de backend mantém todo estado comprometido e não reexecuta efeitos externos sem reconciliação.

**Evidência exigida:** diff revisado + log dos cenários + artefatos/trace quando aplicável, todos vinculados ao SHA do PR.

**Rollback:** Preservar baseline/fixtures e compatibilidade; release feature-gated. Alterações de schema exigem migração e teste de recuperação. Não afrouxar gates para obter verde.


## 8. Programa para superar o Kimi de forma demonstrável

### Duas comparações diferentes

**Orquestração:** mesmo modelo base, ferramentas, dados e teto de custo, comparando um agente, fan-out fixo, DAG, seleção adaptativa e replanning. Esse experimento isola o valor do seu sistema.

**Produto:** acesso autorizado ao Kimi Agent Swarm real, com versão/data, parâmetros, tarefas, entradas, tempo limite e custos comparáveis. Consultar apenas a API do modelo Kimi não é testar o produto Agent Swarm. Resultados públicos históricos não substituem uma comparação pareada ao vivo. Na ausência de acesso, rotular comparação indireta ou não executada.

A referência histórica K2.5 descreve PARL e otimização do trabalho paralelo. Copiar prompts e papéis não reproduz esse treinamento. Neste projeto, primeiro construir traces e avaliações confiáveis; depois testar políticas aprendidas do coordenador, mantendo workers e gates sob controle. Fonte: EXT-04.

### Dados e protocolo

Usar benchmarks públicos identificados por versão, incluindo o DeepResearch Bench de arXiv:2506.11763, e um conjunto privado novo, multilíngue e difícil. Acrescentar tarefas de documentos longos, evidência contraditória, atualização temporal, código, dados e artefatos; uma vitória apenas em pesquisa textual não autoriza dizer que o produto supera tudo em todas as tarefas.

Separar train/dev/test por origem, família de tarefa, fonte e período. Nunca ajustar prompts, thresholds, memória ou roteamento com base em respostas do held-out. Executar várias repetições pareadas; determinar tamanho amostral e efeito detectável por piloto/power analysis, não por uma quantidade arbitrária de casos. Contar timeouts, incompletos e falhas como resultados, não removê-los.

### Métricas e decisão

Escolher antes um desfecho primário de cumprimento dos requisitos com evidência. Reportar também suporte real de citações, cobertura material, exatidão numérica/temporal, taxa de conclusão, desempenho sob falha, custo por tarefa bem-sucedida, latência p50/p95 e consumo de ferramentas. Calibrar juízes automáticos com revisão humana cega; não usar só a nota de um LLM.

Exemplo de hipótese a pré-registrar, não resultado prometido: ganho absoluto de pelo menos 10 pontos percentuais em sucesso fundamentado no mesmo orçamento, **ou** custo pelo menos 30% menor sob uma margem pré-definida de não inferioridade de qualidade. Selecionar uma hipótese primária antes de ver o teste; corrigir múltiplas comparações quando aplicável e publicar intervalos de confiança e todos os runs.

A alegação aceitável tem escopo: “superior ao baseline X, versão Y, no conjunto Z, sob orçamento W, com intervalo e protocolo publicados”. Não usar “SOTA de SOTA” como substituto de comparação com sistemas contemporâneos e independentes.

## 9. O que preservar e o que não fazer

Preservar schemas, compilador de DAG, normalização/hashes onde corretos, artefatos legíveis, boa parte da suíte, hooks nativos e o selo final já implementado. Reusar o offline como baseline reprodutível e modo econômico.

Não renomear heurísticas como inteligência semântica, não tratar arquivos de agente como agentes executados, não empilhar modelos/revisores sem ablação, não declarar testes executados porque aparecem no JSON e não liberar plugins de terceiros por presumir que a MIT da raiz cobre tudo.

Não substituir todo o armazenamento por um cluster antes de provar necessidade. Não usar forks de instâncias do host para fingir que seu limite documentado não existe. Não dar ao modelo controle de secrets, políticas, banco ou aprovação final de seus próprios artefatos.

## 10. Correspondência com SW-00 a SW-18

Os estados abaixo são históricos do arquivo STATUS no SHA auditado. “DONE” histórico não afirma satisfação de todos os novos cenários de segurança e integração.


**SW-00 — DONE_HISTORICO:** KS-002, KS-009, KS-030, KS-079

**SW-01 — DONE_HISTORICO:** KS-004, KS-005, KS-045, KS-046, KS-073, KS-078, KS-079

**SW-02 — DONE_HISTORICO:** KS-003, KS-010, KS-018

**SW-03 — DONE_HISTORICO:** KS-002, KS-011, KS-012, KS-062

**SW-04 — PENDENTE_HISTORICO:** KS-003, KS-008, KS-023, KS-024, KS-025

**SW-05 — PENDENTE_HISTORICO:** KS-008, KS-010, KS-019, KS-022, KS-023, KS-025, KS-026, KS-034, KS-035, KS-039

**SW-06 — PENDENTE_HISTORICO:** KS-002, KS-007, KS-009, KS-012, KS-020, KS-021, KS-022, KS-027, KS-028, KS-072

**SW-07 — PENDENTE_HISTORICO:** KS-029, KS-048, KS-066, KS-076

**SW-08 — PENDENTE_HISTORICO:** KS-015, KS-032, KS-044, KS-048, KS-055, KS-067, KS-068

**SW-09 — PENDENTE_HISTORICO:** KS-033

**SW-10 — PENDENTE_HISTORICO:** KS-040, KS-065, KS-069

**SW-11 — PENDENTE_HISTORICO:** KS-002, KS-013, KS-014, KS-015, KS-016, KS-035, KS-036, KS-037, KS-038, KS-039, KS-040, KS-041, KS-042, KS-043, KS-044, KS-047, KS-049, KS-050, KS-051, KS-052, KS-053, KS-054, KS-055, KS-056, KS-057, KS-063

**SW-12 — PENDENTE_HISTORICO:** KS-013, KS-051, KS-057, KS-059, KS-060, KS-061, KS-062, KS-063, KS-064

**SW-13 — PENDENTE_HISTORICO:** KS-017, KS-018, KS-031, KS-039, KS-045, KS-046, KS-047, KS-072

**SW-14 — PENDENTE_HISTORICO:** KS-029, KS-077

**SW-15 — PENDENTE_HISTORICO:** KS-037, KS-052, KS-058, KS-069, KS-070

**SW-16 — PENDENTE_HISTORICO:** KS-006, KS-071, KS-073, KS-074, KS-075, KS-076

**SW-17 — PENDENTE_HISTORICO:** KS-001, KS-004, KS-045, KS-072, KS-073, KS-078, KS-079

**SW-18 — PENDENTE_HISTORICO:** KS-080


## 11. Fontes e arquivos complementares

Os achados concretos e suas fontes fixadas no commit estão em `AUDITORIA_EVIDENCIAS.md`; a extensão exata da leitura está em `COBERTURA_AUDITORIA.json`.

- **EXT-01** [Claude Code — Workflows](https://code.claude.com/docs/en/workflows) — Contrato e limites atuais do host; não confundir workflow com um runtime JavaScript genérico.

- **EXT-02** [Claude Code — Hooks reference](https://code.claude.com/docs/en/hooks) — Conferência do formato de hooks nativos; command/args não foi tratado como defeito.

- **EXT-03** [Claude Code — Plugins reference](https://code.claude.com/docs/en/plugins-reference) — Conferência do manifesto e suporte a workflows.

- **EXT-04** [Moonshot AI — Kimi K2.5](https://www.kimi.ai/blog/kimi-k2-5) — Referência histórica do swarm original e do PARL; não é afirmação sobre o modelo mais recente em setembro de 2026.

- **EXT-05** [DeepResearch Bench: A Comprehensive Benchmark for Deep Research Agents](https://arxiv.org/abs/2506.11763) — Identificador inequívoco do benchmark; não confundir com outros trabalhos de nome semelhante.

- **EXT-06** [SQLite — Write-Ahead Logging](https://sqlite.org/wal.html) — Limites de concorrência/durabilidade e correção WAL-reset; verificar a biblioteca efetivamente instalada.

- **EXT-07** [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — Referência para controles de rede e redirecionamento.
