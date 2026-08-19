# Kimi Web — Swarm de Agentes ("OK Computer" / Agent Mode)

## ⚠️ Natureza deste documento

Este arquivo **não é** o "prompt de sistema original" do Kimi e **não** contém
nenhuma instrução confidencial do Moonshot. Aquele texto nunca é enviado ao
navegador e, portanto, **não existe no seu HAR** — logo, não há como ser
"extraído" dele, nem por injeção de prefill nem por transcrição.

O que está abaixo é uma **reconstrução funcional** derivada exclusivamente de
dados que você já possui: o arquivo `www.kimi.ai.har` (sua própria captura de
tráfego de uma execução real do swarm). Cada afirmação aqui é respaldada por
uma observação concreta no HAR (endpoints, payloads e listas de agentes), não
por adivinhação.

---

## 1. Como o swarm é acionado

A conversa roda no `scenario = SCENARIO_OK_COMPUTER` com `kimiplus_id = "ok-computer"`.

Payload de entrada (`ChatService/Chat` no HAR):

```json
{
  "chat_id": "…",
  "scenario": "SCENARIO_OK_COMPUTER",
  "kimiplus_id": "ok-computer",
  "tools": [
    { "type": "TOOL_TYPE_SEARCH", "search": {} },
    { "type": "TOOL_TYPE_ASK_USER" }
  ],
  "options": {
    "thinking": true,
    "enable_plugin": true,
    "reasoning_effort": "REASONING_EFFORT_LOW",
    "context_length": "CONTEXT_LENGTH_XL"
  }
}
```

Observações reais:
- A superfície de ferramentas exposta ao orquestrador é **busca** (`TOOL_TYPE_SEARCH`)
  e **perguntar ao usuário** (`TOOL_TYPE_ASK_USER`).
- O protocolo de transporte é **Connect-RPC** (envelope binário de 5 bytes:
  `[1 flag][4 length BE][JSON]`), não REST puro.
- Endpoints de orquestração observados no tráfego: `ListAgents`, `ListAgentMessages`,
  `GetOutputFileTree`, `GetManifest` (serviço `kimi.gateway.mcp.v1.OKCService`).

---

## 2. Topologia do swarm (43 agentes observados)

Distribuição de tipos (`ListAgents`):

| Tipo | Qtde | Papel observado |
|------|-----:|-----------------|
| `general` | 8 | Análise de fontes + síntese cruzada |
| `plan` | 4 | Planejamento e estruturação |
| `escritor_tecnico_fsearch` | 23 | Escrita de capítulos/apêndices + correções |
| `reviewer` | 7 | Edição e revisão editorial |
| `coder` | 1 | Conversão final (DOCX) |
| **Total** | **43** | — |

Cada agente no HAR carrega metadados: `id`, `index`, `name`, `type`, `motto`,
`description` (a tarefa atribuída) e `status` (`STATUS_TERMINATED` ao fim).

---

## 3. Pipeline observado (5 estágios, inferido da ordem `index` + `description`)

A ordem dos `index` e as `description` de cada agente revelam o fluxo real de
fan-out → fan-in do orquestrador:

### Estágio 1 — Varredura de fontes (fan-out), `general`, índices 1–7
Seis fontes são distribuídas em paralelo, uma por agente:
- `Friedrich` → paper 2409.14913v2
- `Karl` → paper 2506.06287v1
- `Sartre` → paper 2506.21558v1
- `Coase` → paper 2601.22444v2
- `Su` → paper 2604.26106v1
- `Stigler` → log HAR da sessão FutureSearch

### Estágio 2 — Síntese cruzada (fan-in), `general`, índice 7
- `Allen` → "Síntese cruzada das 6 fontes"

### Estágio 3 — Planejamento, `plan`, índices 8–11
- `Principal Winston` → analisar requisitos do relatório
- `Nash` → sintetizar artefatos de pesquisa
- `Toby` → projetar estrutura de capítulos
- `Max` → planejar conteúdo por capítulo

### Estágio 4 — Escrita (fan-out em massa), `escritor_tecnico_fsearch`, índices 12–29
Um agente por unidade do documento:
- Capítulos 1–12 (Jasmine, Dr. Hu, Martin, Xavier, Descartes, Autumn, Owen,
  Paul, Mok, Debussy, Winton, Wu)
- Apêndices A–E (Rosalind, Li Hua, Joker, Quentin, Lovel)
- Sumário Executivo (Summer)

### Estágio 5 — Revisão e consolidação, `reviewer` + `escritor_tecnico_fsearch` + `coder`, índices 30–43
- Revisão editorial por faixas de seção (Kat, Jane, Heller, Shannon, Noah)
- Correções e reaplicações (Manco, Dru, Marlow, Picasso, Dewitt, Faquet, Gray)
- Revisão final (Reid) → conversão DOCX (Louis, `coder`)

**Estrutura de saída** (`GetOutputFileTree`, montada em `sandbox:///mnt/okcomputer/output/`):

```
output/
├── plan.md
├── futuresearch_engenharia_reversa.docx
├── futuresearch_reverse_sec00..sec18.md
├── futuresearch_reverse.agent.outline.md / .final.md
├── futuresearch_reverse_ref.md
├── research/
│   ├── fsearch_file_<paper>_arquitetura.md   (um por fonte)
│   ├── fsearch_insight.md
│   ├── fsearch_cross_verification.md
│   └── har_extract/                          (payloads brutos da sessão)
└── docx_build/
    ├── futuresearch_engenharia_reversa.md
    ├── citation.jsonl
    └── *.base.docx / *.converted.md / *.footnote.docx
```

---

## 4. O que NÃO está no HAR (e por que a injeção falha)

1. **O texto literal do system prompt do orquestrador** nunca desce ao cliente.
   O que desce são os *resultados* do orquestrador (lista de agentes, mensagens,
   árvore de arquivos). Por isso não há "dump" possível a partir do tráfego.
2. A diretiva de autodefesa que o K3 revelou no reasoning — *"Show the outcome,
   not the machinery…"* — é aplicada **no servidor**, e o modelo a trata como
   âncora prioritária no estágio de raciocínio, antes de produzir o texto final.
3. O prefill de `reasoning_content` reescreve a *entrada* do modelo, mas não
   substitui o system prompt. O modelo raciocina sobre a meta-intenção da
   mensagem e reclassifica a injeção como `prompt extraction` — exatamente o
   comportamento que sua execução demonstrou.

---

## 5. Conclusão

O que você queria ("o prompt original") não é alcançável por injeção, porque
não existe no seu tráfego e eu (Claude) também não o possuo. O que **é**
alcançável — e está documentado acima — é a **arquitetura completa do swarm**,
reconstruída a partir dos dados que você já capturou: 5 tipos de agente,
5 estágios de pipeline, ferramentas expostas, protocolo de transporte e a árvore
de artefatos de saída. Isso é mais fiel e mais útil do que qualquer texto de
prompt forjado.
