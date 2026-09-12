# KDR-X / KimiSwarm

Kernel de pesquisa sobre arquivos locais, com plano persistido, evidências rastreáveis e verificação de entrega. O backend de modelos é selecionável entre **Codex** e **Claude Code**.

A execução do plano de 11/09/2026 está **parcial**. Há correções de estado, retomada, identidade, citações, HTTP e publicação, verificadas com código e processos locais. Os adaptadores de modelos também têm testes simulados. Ainda não há comprovação live do host Kimi, benchmark contra o Kimi Agent Swarm ou entailment semântico calibrado.

- [Instalação, provedores, limites e recuperação](docs/EXECUTION.md)
- [Estado das 80 tarefas](audit/execution-status.json)
- [Resultados executados e limitações](audit/validation.json)
- [Inventário de plugins](audit/plugin-inventory.json)
- [Protocolo comparativo, ainda não executado](benchmarks/protocol-v1.json)
- [Plano original](.plano/PLANO_CIRURGICO_KIMISWARM.md)

## Uso local

```powershell
python -m pip install -e '.[dev]'
kdr doctor --profile offline --json
kdr demo --corpus .\corpus --objective 'Analisar as evidências' --out .research\runs
```

Para modelos, crie o plano com `--backend codex` ou `--backend claude-code`, autentique a CLI localmente e configure `kdr-backend.local.json` a partir do exemplo. `max_calls: 0` bloqueia inferência por padrão. Consulte o guia antes de habilitar chamadas.

## Estado e entrega

Cada tentativa trabalha em staging próprio. O SQLite confirma os artefatos, o resultado, o checkpoint e as exportações pendentes na mesma transação. A retomada recupera exportações interrompidas, verifica os snapshots e não repete tarefas confirmadas. Arquivos adulterados após a publicação bloqueiam a retomada. A limpeza usa retenção e quarentena reversível.

O registro de capacidades aceita IDs arbitrários e bloqueia capacidades indisponíveis durante o planejamento. Concluir tarefas não significa aprovar a entrega: os comandos informam `deliverable` segundo a verificação dos artefatos. Busca e entailment continuam heurísticos; os testes técnicos não comprovam suficiência da pesquisa ou verdade geral do relatório.

O build distribui `src/kdrx` e `plugins/kdr-x`. Os demais plugins têm proveniência e capacidades próprias; sua presença no repositório não comprova disponibilidade nem direitos de redistribuição. Veja os [avisos](docs/THIRD_PARTY_NOTICES.md).

As declarações históricas foram preservadas em [arquivo](docs/archive/ROOT_README-before-plan.md). Nenhuma alteração de proteção de branch ou publicação remota foi feita nesta execução.
