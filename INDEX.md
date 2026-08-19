# Kimi Swarm — Índice Mestre da Investigação

> Organização completa de todo o material extraído. Cada entrada abaixo tem origem
> verificada (HAR, zip, skill baixada ou sondagem funcional).

---

## ⚠️ ALERTA DE SEGURANÇA (leia primeiro)

Durante a extração encontrei **uma API key em texto puro** no arquivo
`.agent-gw.json` (dentro de `portal-overlay.zip`):

```
base_url: https://agent-gw.kimi.com/coding
api_key: sk-kimi-***REDACTED***
kimi_chat_id: 1a018d24-... (seu chat id)
```

**Ação recomendada**: trate essa chave como **comprometida**. Revogue-a na sua conta
Kimi/Moonshot e gere uma nova. Ela dá acesso ao gateway de agentes (`agent-gw.kimi.com`),
o mesmo usado pelos plugins de dados. Não está reproduzida em nenhum arquivo organizado
abaixo — está apenas sinalizada aqui.

Outra credencial exposta: `prompts/run_kimi_dir.py` contém uma chave `wk-ez3b...`
(diferente, endpoint `modal.com`). Remova antes de compartilhar qualquer coisa.

---

## Estrutura do repositório (organizada)

### 1. `skills/` — 269 skills oficiais (fonte primária, completa)
Baixadas via `SkillService`. **Identidade 100% confirmada** com o sandbox (comparei
269/269 nomes — zero diferença). As relevantes ao swarm:

| Skill | Papel |
|-------|-------|
| `deep-research-swarm` | **Orquestrador do swarm de pesquisa** (rotas A/B/C/D, 7 fases) |
| `deep-research` | Pesquisa profunda "single-agent" (versão não-swarm) |
| `report-writing` / `paper-writing` | Escrita (handoff da Fase 7) |
| `general-writing` | Escrita criativa (fiction) |
| `vibecoding-general-swarm` / `vibecoding-webapp-swarm` | Orquestração de coding |
| `backend-building-swarm` / `webapp-building-swarm` | Scaffold de apps |
| `swarm-workspace` | Contrato filesystem 2-tier (git worktrees) |
| `skill-creator-swarm` | Criação/avaliação de skills |
| `docx` / `pdf` / `xlsx` / `kimi-slides` | Skills de artefato |
| `kimi-help-center` / `kimi-widget` | Skills de runtime do sandbox |

### 2. `extracted/plugins/` — os 8 plugins de dados (novo)
Código-fonte **completo** de cada plugin (script + skill + manifesto + bundle):

| Plugin | Conteúdo extraído |
|--------|-------------------|
| `scholar` | `scholar_tool.py` + `SKILL.md` + `kimi.plugin.json` (v0.1.4) |
| `sec_edgar` | filings SEC / XBRL / insider trades |
| `imf` | WEO/COFER macroeconômico |
| `world_bank_open_data` | indicadores de desenvolvimento |
| `yahoo_finance` | ações / métricas / ownership |
| `audio_generation` | TTS / efeitos sonoros |
| `image_generation` | texto→imagem |
| `github` | MCP oficial (manifesto apenas, sem script local) |

**Padrão descoberto**: todo plugin segue a mesma arquitetura — `scripts/*_tool.py`
(CLI `describe`/`call` que fala com o **agent-gw SDK**), `skills/*/SKILL.md` (instruções),
`kimi.plugin.json` (manifesto com schema `catalog.deva.msh.team`). O endpoint é
`agent-gw.kimi.com/coding` via SDK Python `agent_gw`.

### 3. `extracted/runtime/` — código de runtime do sandbox (novo)
O código real que roda o sandbox "moonbox" (codinome Moonshot):

| Arquivo | Função |
|---------|--------|
| `version.json` | Manifesto: base image `moonbox-okc:project-20260811-2`, portas (kernel 8888, CDP 9223, VNC 6080), `compat_paths` |
| `start-moonbox-project-sandbox.sh` | Bootstrap (exec `/init`) |
| `kernel_server.py` | **Servidor FastAPI do Jupyter kernel** (reset/interrupt/execute na porta 8888) |
| `jupyter_kernel.py` | Gerenciador do kernel Jupyter |
| `browser_guard.py` | Guarda do navegador (28KB — automação pyautogui/Chrome) |
| `project-cdp-proxy.py` | **Proxy CDP** (reescreve URLs do Chrome DevTools Protocol, porta 9223) |
| `patch-browser-guard.py` / `patch-kernel-server.py` | Patches de bootstrap (adicionam try/except e rota `/kernel/execute`) |
| `utils.py` | `get_screensize()` + `run_command()` |
| `ipython.py.init` | Init do IPython (matplotlib + fontes CJK + paleta de cores) |

### 4. `extracted/user_skills/` — skill do usuário (novo)
`unnamed-skill` = **`ai-persona-crafter`** — skill que o usuário (você) tinha instalada
em `/app/.user/skills/`. Gera documentos de persona/character para LLMs
(system-prompt style), com `structure_contract.md` e `style_contract.md` derivados de
um artefato chamado "ENI for Kimi K3.md". É a **única skill de usuário** presente no
sandbox (confirmado: `user_skills: []` na listagem do orquestrador era o estado em outra
sessão).

### 5. `prompts/` — 8 prompts únicos (já analisados)
Ver `prompts_analysis` abaixo. Resumo: `Kimi K3 system prompt.txt` = system prompt base
autêntico; `kimi-3.md`/`kimi3.md` = o mesmo em Markdown; `mooncode_runtime_model_planner.mbt`
= código MoonBit (não prompt); `jury-tool.ts` = código TS (não prompt).

### 6. Documentos de análise (produzidos por mim)

| Arquivo | Conteúdo |
|---------|----------|
| `KIMI_SWARM_ORCHESTRATOR_PROMPT.md` | **Prompt consolidado** do orquestrador (19 seções, fonte rastreada) |
| `swarm_prompt_reconstructed.md` | Reconstrução das seções da sondagem funcional |
| `swarm_analysis.md` | Cruzamento HAR + skill (43 agentes reais + pipeline) |
| `swarmprompt.md` | Reconstrução inicial |
| *(este)* `INDEX.md` | Índice mestre |

### 7. Capturas de tráfego

| Arquivo | Conteúdo |
|---------|----------|
| `www.kimi.ai.har` | Execução real do swarm (43 agentes, `ListAgents`, output tree) |
| `harprompt.har` | Sondagem funcional (sections do orquestrador emitidas) |
| `folder_listing.txt` | Listagem `maxdepth 2` do sandbox |
| `full_filesystem_listing.txt` | Listagem recursiva completa (358k linhas) |

### 8. Zips brutos (originais, preservados)

| Zip | Conteúdo | Status |
|-----|----------|--------|
| `portal-overlay.zip` | 8 plugins + user skill + **agent-gw.json (API key!)** | extraído |
| `opt.zip` | moonbox runtime + version.json | extraído |
| `user_folder.zip` | unnamed-skill + auth dirs | extraído |
| `app_all.zip` | `/app` completo (skills + runtime .py) | extraído (runtime) |
| `agents_backup.zip` | `/mnt/agents` (plugins duplicados) | redundante |
| `agents-skills-source-only.tar.gz` | skills source (3578 arquivos) | = `skills/` |
| `home_kimi.zip` | `/home/kimi` (60928 entradas, 99% cache) | cache |
| `run_backup.zip` | estado s6 `/run` | infra |
| `deep-research-files.zip` / `deep-research-swarm-files.zip` | skills (idênticas às de `skills/`) | redundante |
| `root_kimi.zip` | aponta para `.agent-gw.json` (34 bytes) | redundante |

---

## Arquitetura completa (consolidada)

```
┌─ Camada 0: System prompt base (Kimi K3) ────────────────┐
│  "Show the outcome, not the machinery" + referências    │  ← prompts/Kimi K3 system prompt.txt
├─ Camada 1: Orquestrador (runtime OK Computer) ──────────┤
│  6 agent types + 4 estágios + subagent mechanics        │  ← harprompt.har (sondagem)
├─ Camada 2: Skills (baixáveis) ──────────────────────────┤
│  deep-research-swarm + 268 outras                       │  ← skills/
├─ Camada 3: Plugins (baixáveis) ─────────────────────────┤
│  8 conectores de dados via agent-gw                     │  ← extracted/plugins/
├─ Camada 4: Runtime do sandbox (moonbox) ────────────────┤
│  kernel_server + cdp_proxy + browser_guard              │  ← extracted/runtime/
└──────────────────────────────────────────────────────────┘
```

## Conclusão da investigação

**Completa.** Você tem agora, com fonte rastreável e identidade verificada:

1. O **system prompt base** (autêntico, confirmado pela diretiva que vazou).
2. O **orquestrador** (6 presets + framework + mecânica, via sondagem funcional).
3. As **269 skills** (100% idênticas às do sandbox).
4. Os **8 plugins** (código-fonte completo).
5. O **runtime do sandbox** (kernel, CDP, browser, version.json).

O único item inacessível permanece o **texto verbatim** do system prompt server-side
(redação exata, não reconstruída). Tudo o mais está documentado.
