# BLOCKERs imediatos

## B-01 — Credenciais vivas e material sensível no Git
**CRITICAL**

- Revogar/rotacionar as credenciais antes de qualquer edição Git.
- Transferir o corpus forense para armazenamento privado e criptografado fora do repo.
- Remover os paths da árvore e de todo o histórico com git-filter-repo.
- Invalidar clones antigos e habilitar push protection.
- Adicionar gitleaks e detect-secrets localmente e em CI.

## B-02 — Plugin KDR-X não é instalável como declarado
**CRITICAL**

- Criar commands/ no plugin ou migrar entrypoints para skills.
- Criar workflows/ reais.
- Usar ${CLAUDE_PLUGIN_ROOT} para todos os paths.
- Fornecer wrapper/bin autocontido e plugin doctor E2E.

## B-03 — Hooks de lifecycle não executam os gates prometidos
**CRITICAL**

- Criar hooks/hooks.json compatível com o payload oficial.
- Consumir stdin real por evento.
- Registrar TaskCreated, TaskCompleted, SubagentStop e Stop.
- Descobrir o active run no Stop e executar hook_stop de verdade.
- Testar o wrapper como subprocess com exit code 2.

## B-04 — Não existe swarm paralelo executável
**CRITICAL**

- Implementar Dynamic Workflows JavaScript como control plane.
- Usar Python para schemas/state/gates, não como substituto dos agents.
- Separar workflow de plan e execute.
- Executar cada wave com pipeline() e resultados estruturados.

## B-05 — CLI principal possui comandos quebrados/no-op
**HIGH**

- Adicionar cmd_plan.
- Implementar cmd_run carregando plan/manifest.
- Implementar verify/report reais.
- Implementar monitor ou removê-lo do release.
- Adicionar testes subprocess para todos os commands.

## B-06 — Gates epistemológicos não bloqueiam
**HIGH**

- Adicionar severidade blocking/advisory por check.
- Existência/identidade/span/claim material devem bloquear.
- COI/currency podem ser advisory conforme risk policy.
- Aplicar política por route e risk level.

## B-07 — Sem CI, branch protection ou prova independente dos testes
**HIGH**

- Adicionar CI/security/plugin-e2e/evals workflows.
- Habilitar branch protection e required checks.
- Exigir PR/review.
- Corrigir user.name/user.email e assinar commits quando possível.
