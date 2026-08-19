# Orquestrador — como skill Kimi

Esta pasta está organizada no **padrão de uma skill Kimi** (a anatomia definida
por `skill-creator-swarm`): `SKILL.md` na raiz + `references/` + `assets/`.

## Anatomia

```
orchestrator/
├── SKILL.md                        ← skill principal (frontmatter name/description + workflow)
├── references/                     ← documentação que o agente lê enquanto trabalha
│   ├── agent-types/                ← spec completo dos 6 subagentes (.md)
│   │   ├── general.md  coder.md  explore.md
│   │   ├── plan.md  reviewer.md  verifier.md
│   ├── agent_workflow.md           ← identidade do orquestrador + princípios
│   ├── task_execution_framework.md ← os 4 estágios
│   ├── subagent_mechanics.md       ← foreground/background, limites, ferramentas
│   ├── skill_system.md  plugin_system.md  capability_system.md
│   ├── sandbox.md  communication.md  harness_spec.md
│   ├── search_and_current_information.md  human_in_the_loop.md
│   ├── default_standards.md  special_emphasis.md
│   ├── language_consistency.md  timeliness_requirement.md
│   ├── file_paths_and_references.md  skills_create_edit_download_policy.md
│   ├── artifact_output_rules.md  website_delivery_rules.md
│   └── frontend_rendering_protocols.md
└── assets/
    └── raw-json/                   ← JSON verbatim da sondagem (fonte primária)
        ├── agent-types/*.json      ← os 6 agent types exatos
        └── mechanics/*.json        ← as 20 seções exatas
```

## Frontmatter

O `SKILL.md` usa frontmatter YAML (`name` + `description`), exatamente como as
skills oficiais. `name: ok-computer-orchestrator`.

## Origem

Todo conteúdo veio de `harprompt.har` (sondagem funcional), onde o orquestrador
emitiu cada seção em resposta a pedidos por nome. Os `.json` em `assets/raw-json/`
são **verbatim** (só removido o `response_prefix` da persona injetada). Os `.md`
em `references/` são derivações formatadas dos mesmos JSONs.

O texto verbatim do system prompt server-side permanece inacessível — esta skill
documenta o que o orquestrador efetivamente emitiu sob sondagem.
