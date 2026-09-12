# Execução local do plano de 11/09/2026

O backlog original contém 80 tarefas, 400 subtarefas e 160 cenários propostos. Os arquivos originais de `.plano` foram preservados. `audit/execution-status.json` registra o escopo por tarefa; `audit/validation.json` é a fonte dos resultados executados. O plano completo ainda não está certificado.

## Instalação e diagnóstico

Use Python 3.10 ou superior. Neste Windows, a validação usa Python 3.13.15 com SQLite 3.53.1 em `.venv-ks`. SQLite antigo sem a correção exigida usa journal DELETE; solicitar WAL explicitamente nessa versão falha. A base deve estar em disco local. Não compartilhe o arquivo SQLite por NFS/SMB.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[dev]'
.\.venv\Scripts\kdr doctor --profile offline --json
.\.venv\Scripts\kdr doctor --profile live --backend codex --json
.\.venv\Scripts\kdr doctor --profile live --backend claude-code --json
```

`doctor --profile live` consulta instalação e autenticação, sem fazer inferência. Login válido não torna o diagnóstico live aprovado: falta o teste real. `doctor --profile plugin` também exige um round-trip real do host; testes JavaScript emulados não o substituem.

## Claude Code ou Codex

Autentique somente na máquina com `codex login` ou `claude auth login`. O kernel não lê arquivos de credenciais nem os copia para relatórios. O Codex encontrado nesta sessão já estava autenticado via ChatGPT; o Claude Code não estava autenticado. Não foi executada inferência paga durante a implementação.

Copie `kdr-backend.example.json` para `kdr-backend.local.json`, ignorado pelo Git. Escolha `provider: "codex"` ou `"claude-code"`. Configure `max_calls` explicitamente; zero impede qualquer chamada. Um fluxo completo tem cinco chamadas de especialistas sem retry automático. `timeout_seconds` limita cada processo. Alterar o provedor ou o orçamento exige um novo run.

No modo `subscription`, a execução exige autenticação de assinatura reconhecida e remove variáveis de autenticação por API do processo filho. No modo `metered`, somente Claude Code é aceito, com `max_cost_usd` obrigatório dividido entre as chamadas. Codex CLI não oferece aqui um teto monetário verificável, portanto esse modo é bloqueado. Tokens ausentes e custo desconhecido são registrados como desconhecidos. Limites por chamadas não equivalem a limites por tokens.

```powershell
kdr plan --backend codex --objective 'Comparar as evidências de latência' --corpus .\corpus --out .research\runs --json
kdr run --run-dir .research\runs\ID --corpus .\corpus --backend-config kdr-backend.local.json
kdr resume --run-dir .research\runs\ID --corpus .\corpus --backend-config kdr-backend.local.json
kdr verify --run-dir .research\runs\ID
kdr seal --run-dir .research\runs\ID --json
kdr verify-delivery --run-dir .research\runs\ID
```

Para Claude Code, troque o backend na criação do plano e no arquivo local. O fluxo é sobre corpus local: coleta e extração pelo kernel, análise metodológica, contraevidência, lacunas, escrita e revisão por modelos. Os modelos recebem fontes, trechos e claims como contexto; essa informação sai da máquina quando uma execução live é habilitada. A seleção de corpus é responsabilidade do operador. Não selecione diretórios de credenciais.

Os adaptadores usam argv e stdin, saída estruturada, diretório temporário, personalizações desabilitadas e ferramentas restringidas por flags do host. Isso não constitui uma sandbox do sistema operacional para código hostil. O isolamento completo de ferramentas, a integração live e o host Kimi ainda exigem validação. Configuração não suportada deve falhar; não há fallback automático para outro provedor ou fixtures.

## Estado, retomada e recuperação

O SQLite em `runs/.kdr-state.sqlite3` mantém revisões, leases e eventos; JSON é exportação legível. `.blobs` guarda conteúdo por SHA-256. Preserve banco, blobs e diretórios dos runs juntos. Use a API `SQLiteStore.backup(destination)` para backup consistente enquanto a base estiver aberta; copiar apenas o arquivo SQLite em WAL pode perder estado.

O schema SQLite 3 mantém exportações recuperáveis e acrescenta políticas de comunicação, assinaturas, notificações, confirmações e leases de recursos. A atualização de schemas 1/2 cria um backup SQLite consistente em `.schema-backups/` antes do DDL; a integridade do backup é conferida. Falha de backup impede a atualização, e interrupção durante o DDL preserva a versão anterior. Para consulta de rollback, abra o backup com SQLite `mode=ro`; preserve os blobs junto dele. Não execute um runtime antigo em escrita sobre o banco novo.

Cada tentativa usa `.staging/<run>/<attempt>`, com cópias dos inputs e ownership das saídas. O kernel valida os arquivos, sincroniza os blobs e confirma resultado, referências, recibo, checkpoint e exportações pendentes na mesma transação. Um erro de exportação depois do commit interrompe a execução sem repetir a tarefa. Ao reabrir, as exportações pendentes são recuperadas. Isso foi testado com encerramento abrupto de processos e falhas de escrita; não constitui um ensaio de perda física de energia.

`resume` verifica hashes, recibos e identidades no banco; o loader tipado confere fontes, spans, claims, standings e edges contra os snapshots. Uma execução já concluída é retomada sem reescrever resultados ou eventos. O índice de busca só é reconstruído quando necessário. Alterar o corpus original não modifica os snapshots existentes. Arquivos adulterados depois de uma exportação confirmada continuam bloqueados: a retomada não os corrige silenciosamente.

`patch-plan` aceita um `PlanPatch` com `base_revision`, `reason`, `add_tasks`, `remove_tasks`, `dependencies`, `task_budgets`, `required_budget` e `invalidate_tasks`. A transação valida DAG, capacidades e ownership, arquiva a revisão anterior e revoga a entrega até nova verificação. Dois patches da mesma revisão não podem ser aplicados: o segundo exige rebase. Tasks em execução bloqueiam o patch até parada/reconciliação. Um scheduler antigo não pode adquirir leases nem confirmar resultados na nova revisão.

As definições de tarefas concluídas são imutáveis: substituições exigem novos IDs. Recibos de ramos preservados mantêm a revisão e os bytes originais; sua validade é conferida contra o plano arquivado e seus inputs. Invalidações explícitas afetam a tarefa escolhida e os consumidores/descendentes, com histórico em `history/plan-patches/`. Se retrieval precisar ser refeito, ele usa os snapshots comprometidos. Atualização intencional do corpus exige um novo run. O orçamento de um patch não amplia limites nem autoriza chamadas ao provedor.

Exemplo de `patch.json` para reparar o relatório:

```json
{"schema_version":"0.3","base_revision":0,"reason":"Reparar exportação danificada do relatório","invalidate_tasks":["T-SYNTHESIZE"]}
```

```powershell
kdr patch-plan --run-dir .research\runs\ID --patch patch.json
kdr resume --run-dir .research\runs\ID --corpus .\corpus
```

`legacy-status` lê diretórios antigos ou backups ZIP sem inicializar SQLite. `migrate-legacy` exige outro destino, confere hashes declarados, cria e verifica um backup dos bytes originais e importa tudo por transação recuperável. Dados sem hash anterior recebem apenas o registro de observação atual. O resultado é um arquivo histórico somente para leitura, sem tasks certificadas nem entrega elegível. Os arquivos originais e o backup continuam disponíveis para consulta durante rollback; para gerar uma entrega verificada, crie um novo run. Essa importação não converte conclusões antigas em recibos de execução nem retoma automaticamente trabalho legado sem provas.

```powershell
kdr legacy-status --source .research\old-runs\ID
kdr migrate-legacy --source .research\old-runs\ID --runs-root .research\imported
kdr legacy-status --source .research\imported\.legacy-backups\ARQUIVO.zip
```

O importador exige `manifest.json`, `plan.json` e `research_contract.json`, aceita versões 0.2/0.2.0/0.3, rejeita links e aliases de caminhos e limita o snapshot a 512 MiB. O registry legado completo, discos remotos mapeados e recuperação após perda física de energia ainda precisam de aceitação ampliada.

Para recuperar exports perdidos usando o banco e os blobs preservados, existe um comando explícito. Ele substitui os arquivos controlados pelo banco e registra a solicitação. Um backup apenas do SQLite não inclui os blobs; ambos devem ser preservados. A limpeza primeiro apresenta um inventário; `--apply` move dados abandonados para `.quarantine`, sem apagamento definitivo. Referências transitivas dos snapshots e tentativas em execução são preservadas.

```powershell
kdr recover-exports --run-dir .research\runs\ID
kdr gc --runs-root .research\runs --retention-days 7
kdr gc --runs-root .research\runs --retention-days 7 --apply
```

Heartbeats renovam os leases e detectam revogação; a retomada reconcilia leases expirados, preservando o histórico e contabilizando conservadoramente chamadas cujo consumo ficou desconhecido. O pedido versionado `cancel` revoga leases e elegibilidade de entrega em transação. O worker sinaliza o cancelamento ao processo de inferência quando observa a revogação. Threads Python confiáveis podem terminar trabalho já iniciado, mas o fencing rejeita sua publicação. Isso não substitui uma sandbox para código arbitrário.

O selo avalia plano, resultados das tarefas, snapshots, posições exatas dos trechos, citações, pendências críticas e segurança. Bytes verificados, gates da selagem e checkpoint são publicados em conjunto. Os gates originais de cada tarefa permanecem em seus arquivos; uma selagem explícita grava seus próprios gates em `verification/seal/`. Falha posterior revoga a elegibilidade. `verify-delivery` reavalia o certificado localmente; o campo `deliverable` distingue a prontidão da entrega do status das tarefas. Isso certifica integridade técnica; o verificador de entailment continua heurístico e não certifica verdade semântica geral.

O registro de executores valida `task.kind` no planejamento. Há capacidades de retrieval, verificação de fontes, síntese/escrita, análise do standing persistido, exportação de evidências em JSON e gates determinísticos, além dos três tipos de tarefa de modelo. Os IDs são livres e o plano de quatro tarefas é apenas o exemplo padrão. `code` fica indisponível enquanto não houver sandbox validada. Exportação JSON não implica suporte a todos os formatos do backlog.

## Evidências e limites

A comunicação é desabilitada por padrão. Para habilitá-la em um run, crie `coordination-policy.json` com `{"enabled":true}` e uma assinatura, por exemplo `{"task_id":"T-VERIFY","kinds":["SourceDiscovered","ArtifactCommitted"]}`. A política limita quantidade total, taxa por minuto, bytes, assinaturas, fila pendente e tentativas de entrega; depois de configurada, é imutável para esse run.

```powershell
kdr coordination configure --run-dir .research\runs\ID --file coordination-policy.json
kdr coordination subscribe --run-dir .research\runs\ID --consumer reviewer --file subscription.json
kdr coordination publish --run-dir .research\runs\ID --file message.json
kdr coordination receive --run-dir .research\runs\ID --consumer reviewer
kdr coordination status --run-dir .research\runs\ID
```

As mensagens `SourceDiscovered`, `ClaimChanged`, `GapOpened`, `HelpRequested` e `ArtifactCommitted` possuem identidade, revisão, escopo e referências. Descobertas repetidas da mesma URI/hash/escopo convergem para uma notificação. São avisos; não substituem verificação de evidência. `ArtifactCommitted` exige referências já comprometidas e é emitido automaticamente pelo kernel quando a comunicação está habilitada. Pressão da fila produz dead letters/diagnósticos e não repete uma tarefa válida.

A outbox nasce na mesma transação do evento. Leases com tokens impedem confirmação por um consumidor expirado. `Notifications.consume` permite que um handler confiável aplique efeitos no mesmo SQLite e confirme sua inbox em uma única transação; efeitos externos não têm essa garantia. `receive` conserva uma cópia em `coordination/received/` antes de confirmar, permitindo recuperação caso a saída do terminal se perca. Falhas têm retry limitado e dead letter persistida.

Pedidos de ajuda exigem motivo, orçamento finito em todas as dimensões e prazo de aceitação de até um dia. A aceitação aplica um PlanPatch e publica a mensagem em uma única transação, criando a dependência no DAG. Ciclos deixam diagnóstico e nenhuma alteração parcial. Vale a restrição de revisão: tarefas em voo precisam parar/reconciliar antes da alteração. O pedido não aumenta a autorização do provedor; cancelamento automático após o prazo e uso semântico por especialistas live ainda estão pendentes.

`ResourceLocks` oferece aquisição atômica com ordem, expiração e fencing vinculados ao lease da tentativa; não espera segurando parte de um conjunto indisponível. É coordenação dentro de um StateStore local, não uma sandbox nem um lock distribuído. O ganho de qualidade/latência contra comunicação desligada ainda precisa de ablação independente; não há ganho comprovado nesta implementação.

Os testes locais cobrem concorrência, processo interrompido, CAS, fencing, rollback SQLite, limites HTTP, SSRF, bytes do selo e emulação dos adaptadores. `audit/baseline-junit.xml` registra a baseline; `audit/final-junit.xml` registra a implementação. Logs intermediários com falhas foram conservados. O teste inicial da corrida de selo tinha um argumento CLI incorreto; ele foi corrigido antes de validar o defeito e o patch.

O protocolo em `benchmarks/protocol-v1.json` foi congelado antes de qualquer comparação live. Faltam orçamento total, acesso identificado ao Kimi Agent Swarm, dataset privado anotado independentemente e revisão cega. Não há resultado comparativo nem comprovação SOTA. Treinamento do coordenador e múltiplos hosts dependem desses resultados; não são habilitados por contagem de testes.

Referências das interfaces: [Codex não interativo](https://developers.openai.com/codex/noninteractive/), [configuração Codex](https://developers.openai.com/codex/config-reference/), [Claude Code CLI](https://code.claude.com/docs/en/cli-reference), [SQLite WAL](https://sqlite.org/wal.html). As flags também foram conferidas no help das CLIs locais.
