"""Generate an evidence-linked execution register without certifying unrun scenarios."""

import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Each row states both the implemented delta and the remaining acceptance gap.
PROGRESS = {
    1: (
        "Inventário e baseline de 368 testes com JUnit/cobertura; bundles comparados sem execução.",
        "Revisão manual de toda a proveniência externa ainda não certificada.",
        "audit/baseline.json",
    ),
    2: (
        "Regressões dos defeitos centrais registradas antes dos patches; falhas intermediárias preservadas.",
        "Nem todos os 160 cenários propostos foram implementados; primeiro teste de corrida de selo teve argumento CLI corrigido.",
        "tests/test_plan_regressions.py",
    ),
    3: (
        "Envelopes 0.3, PlanPatch e contratos versionados; migração de snapshots com backup e sem inventar recibos.",
        "Todos os envelopes de execução e conversão integral das referências legadas ainda incompletos.",
        "src/kdrx/schemas/versioning.py",
    ),
    4: (
        "Nove plugins inventariados; pacote kdr-x separado; matriz diferencia capacidade local e integração não comprovada.",
        "Direitos de redistribuição dos plugins externos não estabelecidos; substituições independentes pendentes.",
        "audit/plugin-inventory.json",
    ),
    5: (
        "Doctor offline/plugin/live, prova de storage e consulta de autenticação Claude Code/Codex.",
        "Round-trip real do host e inferência live não executados.",
        "src/kdrx/application/capabilities.py",
    ),
    6: (
        "Protocolo versionado com trilhas, desenho pareado, margens e tratamento de falhas.",
        "Baseline Kimi identificado, orçamento total e conjunto privado independente ainda ausentes.",
        "benchmarks/protocol-v1.json",
    ),
    7: (
        "Loader tipado, recibos e histórico; invalidação seletiva explícita, replay do corpus preservado e índice sob demanda.",
        "Atualização intencional do corpus exige novo run; aceitação formal vinculada ao SHA de PR ainda ausente.",
        "tests/test_plan_revisions.py",
    ),
    8: (
        "Identidade, bytes, hash, tamanho, parsing e referências observados pelo kernel; testes declarados pelo agente são rejeitados.",
        "Staging validado para handlers confiáveis; schemas de todos os formatos e sandbox de código hostil pendentes.",
        "src/kdrx/application/artifacts.py",
    ),
    9: (
        "IDs UUID, componentes portáveis, diretório exclusivo e bloqueio de links/travessias.",
        "Prova de mil criações reais concorrentes ainda não executada; teste atual gera mil IDs.",
        "tests/test_plan_regressions.py",
    ),
    10: (
        "Plano persistido e hash/revisão vinculados ao executor; fachadas enviam pedidos ao kernel.",
        "Planner council live e conflitos de importação durante execução precisam de aceitação ampliada.",
        "src/kdrx/application/service.py",
    ),
    11: (
        "Política comum e deliverable separado do status de tasks em runner, run/resume, status JSON e pedidos do kernel.",
        "Aceitação do host real e conclusão semântica independente continuam pendentes.",
        "src/kdrx/application/delivery.py",
    ),
    12: (
        "Bytes, gates próprios da selagem, revisão imutável e checkpoint publicados por transação recuperável; revogação persistida.",
        "Lineage de edição manual do relatório até uma nova revisão do plano e ensaios de perda de energia ainda pendentes.",
        "tests/test_recoverable_publication.py",
    ),
    13: (
        "IDs opacos e mapa de IDs legados; parser aceita espaços/Unicode; citações malformadas bloqueadas.",
        "Migrador completo dos relatórios legados e referências de todas as integrações pendente.",
        "src/kdrx/reporting.py",
    ),
    14: (
        "Trechos por sentença com offsets exatos; gate confere texto contra snapshot e blobs.",
        "Localização completa em tabelas, páginas e extrações multimodais ainda não validada.",
        "src/kdrx/evidence/documents.py",
    ),
    15: (
        "Cobertura lexical separada de suficiência; lacunas críticas não desaparecem por consultas concluídas.",
        "Grafo completo requisito/pergunta/claim e rubricas independentes não implementados.",
        "src/kdrx/retrieval.py",
    ),
    16: (
        "Counterevidence persistida alimenta edges e standing, com motivos de rejeição.",
        "Classificação semântica calibrada e auditoria completa de dupla contagem pendentes.",
        "src/kdrx/runner.py",
    ),
    17: (
        "Transporte com DNS/IP público, peer pinning, redirects revalidados e limites de bytes/tempo.",
        "Prova live de DNS rebinding, deadline rígido do resolvedor e política MIME ampliada pendentes.",
        "tests/test_http_security.py",
    ),
    18: (
        "Objetivo via payload base64/argv e stdin; arquivo global compartilhado removido.",
        "Round-trip no host real e matriz de shells não executados.",
        "tests/test_kernel_requests.py",
    ),
    19: (
        "Fronteiras application/runtime/evidence/integrations extraídas com APIs de compatibilidade.",
        "Extração completa de storage/gates/executores ainda em andamento.",
        "src/kdrx/application/service.py",
    ),
    20: (
        "SQLite, CAS, exports recuperáveis e importação transacional de JSON legado com backup verificado e consulta read-only.",
        "Importação é arquivo histórico sem retomada de sucesso não comprovado; upgrade de schemas/registry e discos remotos mapeados pendentes.",
        "tests/test_legacy_migration.py",
    ),
    21: (
        "Leases, fencing, heartbeats, reconciliação de expiração, consumo desconhecido conservador e cancelamento por conexão externa.",
        "Consumidores de notificações com deduplicação persistida e dead-letter ainda pendentes.",
        "tests/test_runtime_leases.py",
    ),
    22: (
        "Staging por tentativa, blobs antes do commit, publicação recuperável, bloqueio de aliases e coleta com retenção/quarentena.",
        "Isolamento do sistema operacional para código hostil e durabilidade após perda física de energia não certificados.",
        "tests/test_runtime_maintenance.py",
    ),
    23: (
        "Registry executado no planejamento; plano com seis IDs arbitrários, análise de claims e exportação JSON verificado.",
        "Backend code continua bloqueado sem sandbox; exportações além de JSON e especialização semântica completa pendentes.",
        "tests/test_executor_registry.py",
    ),
    24: (
        "Briefs levam identidade, orçamento e políticas; inferência recebe contexto explícito e ferramentas restringidas.",
        "ExecutionSpec tipada completa e enforcement por sandbox do sistema operacional pendentes.",
        "src/kdrx/integrations/model_cli.py",
    ),
    25: (
        "Adaptadores Claude Code e Codex com stdout estruturado, recibos, timeout e seleção explícita.",
        "Nenhuma inferência real executada; integração de host e isolamento ainda não certificados.",
        "tests/test_model_cli.py",
    ),
    26: (
        "Quatro workflows reduzidos a fachadas; fala de agente não autoriza selo.",
        "Entrega de recibo autenticado dentro do host e round-trip real pendentes.",
        "tests/test_workflows.py",
    ),
    27: (
        "Execução concorrente real por dependências prontas; teste com barreira de quatro handlers.",
        "Semáforos globais por provedor e medição live de throughput pendentes.",
        "tests/test_scheduler_concurrency.py",
    ),
    28: (
        "Backoff/deadline, timeout/teto de saída de inferência, cancelamento observado por heartbeat e rejeição de resultados tardios.",
        "Cancelamento de efeitos arbitrários em threads e teste live da árvore completa de processos pendentes.",
        "tests/test_model_cli.py",
    ),
    29: (
        "Reservas compartilhadas e idempotentes; chamadas limitadas; uso desconhecido não vira custo zero.",
        "Limites de tokens/cache/downloads e reconciliação monetária multirrun/provedor incompletos.",
        "src/kdrx/runtime/store.py",
    ),
    30: (
        "Mutação transacional de sessões; corrupção do registry bloqueia; preservação de sessões concorrentes.",
        "Importação/recuperação integral do registry, expiração e aceitação de host pendentes.",
        "src/kdrx/native_hooks.py",
    ),
    31: (
        "Restrições de inferência por flags de host e transporte HTTP validado.",
        "Sandbox obrigatória do SO, broker de ferramentas, ACL/mounts e provas de escape NÃO implementados.",
        "src/kdrx/integrations/model_cli.py",
    ),
    32: (
        "PlanPatch transacional, histórico imutável, CAS, capacidades/DAG/ownership e invalidação seletiva; leases e recibos vinculados à revisão.",
        "Patches exigem fronteira sem tasks em voo; replanejamento automático e reconciliação de todos os tipos de orçamento ainda pendentes.",
        "tests/test_plan_revisions.py",
    ),
    34: (
        "DAG com cinco especialistas e E2E simulado sobre corpus real.",
        "Execução com cinco chamadas reais, isolamento e orçamento autorizado pendentes.",
        "tests/test_model_cli.py",
    ),
    35: (
        "FetchResponse tipada com bytes, status, headers, cadeia, duração e erros tipados de transporte.",
        "Todos os adapters ainda não convergiram para paginação/retry/cache e envelope único.",
        "src/kdrx/integrations/http.py",
    ),
    36: (
        "OpenAlex tolera primary_location.source nulo.",
        "Paginação, expansão bounded e testes live de contratos pendentes.",
        "tests/test_adapters.py",
    ),
    37: (
        "Crossref conserva data completa quando presente e marca precisão anual sem inventar janeiro.",
        "Resolução de versões e metadados completos em todos os provedores pendentes.",
        "src/kdrx/adapters.py",
    ),
    40: (
        "Snapshots bruto/extraído locais armazenados por SHA-256 e usados na retomada.",
        "Snapshots HTTP versionados e exportação portátil de todas as fontes ainda incompletos.",
        "src/kdrx/runtime/blobs.py",
    ),
    41: (
        "DocumentIR com offsets e blocos; código Markdown preservado; PDF sem texto falha explicitamente.",
        "OCR, tabelas/células completas, figuras e validadores de todos os formatos pendentes.",
        "src/kdrx/evidence/documents.py",
    ),
    43: (
        "Parâmetros ref/source deixaram de ser removidos genericamente; aliases de fontes preservados.",
        "Políticas de canonicalização por domínio e near-duplicate auditado pendentes.",
        "src/kdrx/corpus.py",
    ),
    45: (
        "Inventário estático separado dos plugins externos com dependências, endpoints e limitações.",
        "Auditoria semântica de cada ferramenta, autorização e contratos live não concluídos.",
        "scripts/audit_plugins.py",
    ),
    46: (
        "Auto-instalação latest removida dos scripts de imagem/áudio; capacidades desabilitadas.",
        "Build autorizado com dependências pinadas, isolamento e geração real não disponíveis.",
        "plugins/image_generation/scripts/image_generation_tool.py",
    ),
    49: (
        "Heurística de claims ampliada para português e preservação de escopo composto.",
        "Decomposição semântica PT/EN calibrada e anotada independentemente pendente.",
        "src/kdrx/claims.py",
    ),
    50: (
        "Negação oposta derruba overlap; documentação retira garantia semântica.",
        "Modelo NLI/LLM calibrado, corpus independente e ablação ainda não implementados.",
        "src/kdrx/verification.py",
    ),
    51: (
        "Divergências numéricas distinguem escopos temporais em casos básicos.",
        "Unidades, denominadores, arredondamento, moeda e recálculos tipados completos pendentes.",
        "src/kdrx/claims.py",
    ),
    52: (
        "Escopo temporal compara datas do evento no trecho; data editorial não substitui evento.",
        "Event time completo, versões e validade temporal por domínio pendentes.",
        "src/kdrx/claims.py",
    ),
    55: (
        "Busca de contraevidência real no corpus e especialista configurável.",
        "Estratégia adversarial por risco, orçamento por lacuna e validação independente pendentes.",
        "src/kdrx/runner.py",
    ),
    57: (
        "Detecção de afirmações qualitativas não registradas e bloqueio de texto vazio/citação malformada.",
        "Cobertura semântica de toda sentença, negações complexas e causalidade não certificada.",
        "src/kdrx/reporting.py",
    ),
    58: (
        "Revalidação invalida selo e hashes denunciam mudança de evidência.",
        "Grafo completo de lineage e propagação incremental de retratação não implementados.",
        "src/kdrx/application/delivery.py",
    ),
    60: (
        "Writer e reviewer são tarefas distintas e chamam o adaptador de modelos selecionado.",
        "Provas live, fixer separado com laços limitados e ablação de qualidade pendentes.",
        "src/kdrx/application/live.py",
    ),
    62: (
        "Certificado de bytes, plano, grafo e política; verify-delivery funciona sem modelo/rede.",
        "Bundle portátil autocontido com todos os blobs e revisões, assinatura e compatibilidade pendentes.",
        "src/kdrx/application/delivery.py",
    ),
    63: (
        "Reprodução de cálculo resolve hashes para conteúdo real; hash sozinho não é input.",
        "Execução isolada de scripts, unidades e integração de todos os ledgers pendentes.",
        "src/kdrx/analysis.py",
    ),
    65: (
        "Contexto explícito com fontes, spans, claims, pareceres e limite de bytes.",
        "Packs mínimos por relevância, tokenização, compactação/expansão auditável e cache pendentes.",
        "src/kdrx/application/live.py",
    ),
    71: (
        "Hard negatives de regressão para negação, citações, números e identidade.",
        "Dataset privado e anotadores independentes não disponíveis; fixtures do autor não contam como held-out.",
        "tests/test_plan_regressions.py",
    ),
    72: (
        "Provas comportamentais de CAS, concorrência, fencing, rollback por kill, HTTP e selo.",
        "Property testing amplo, mutation testing e matriz de ataques do SO ainda não executados.",
        "tests/test_runtime_store.py",
    ),
    73: (
        "Wheel instalado fora do checkout; diagnóstico, pesquisa, retomada, selo e consumidor exercitados.",
        "Host Claude/Kimi real e sistemas operacionais adicionais não testados.",
        "scripts/verify_distribution.py",
    ),
    77: (
        "Eventos SQLite ordenados e recibos de subprocesso/uso, com custo desconhecido explícito.",
        "Replay determinístico completo e métricas de spans/trace distribuído pendentes.",
        "src/kdrx/runtime/store.py",
    ),
    78: (
        "Lock de dependências com hashes; builds locais comparados e wheel instalado sem editable.",
        "SBOM padronizado, auditoria de dependências, typecheck obrigatório, SHAs de actions, assinatura e publicação pendentes.",
        "audit/distribution.json",
    ),
    79: (
        "README corrigido, histórico preservado, matriz por tarefa e resultados gerados dos JUnits.",
        "Proteção da branch consultada em audit/governance-observation.json; rulesets completos e recuperação em todas as plataformas ainda pendentes.",
        "docs/EXECUTION.md",
    ),
}

NOT_STARTED = {
    33: "Mensagens interagentes tipadas/idempotentes com ciclo de vida não implementadas.",
    38: "GitHub adapter com pin de commit e navegação de código ainda pendente.",
    39: "Ferramentas distintas de busca/fetch/browser e provenance uniforme ainda pendentes.",
    42: "Embeddings neurais e reranking medido não implementados; n-gram continua diagnóstico lexical.",
    44: "Planejamento de pesquisa dirigido por grafo de requisitos ainda pendente.",
    47: "Tipos financeiros por moeda, unidade, período e frequência ainda pendentes.",
    48: "Plano batch por item/campo e snapshots de tabelas ainda pendente.",
    53: "Políticas de qualidade específicas por domínio e validação independente pendentes.",
    54: "Novo grafo de independência por entidade/cadeia causal ainda pendente; heurística anterior permanece.",
    56: "Calibração de confiança com conjuntos independentes não realizada.",
    59: "Outline rastreável a requisitos e EvidencePacks mínimos ainda pendentes.",
    61: "ReportIR validada e montagem mecânica multi-formato ainda pendentes.",
    64: "Exportações de documentos/mídia com abertura real por formato ainda pendentes.",
    66: "Seleção medida de arquitetura e número de agentes depende de avaliações ainda ausentes.",
    67: "Replanejamento automático seguro por lacunas e conflitos ainda pendente.",
    68: "Parada por ganho marginal e risco residual calibrado ainda pendente.",
    69: "Memória governada com proteção de datasets e proveniência ainda pendente.",
    70: "Pesquisa incremental de monitoramento com orçamento e aprovação de mudanças ainda pendente.",
    74: "Benchmark contra single-agent e produto Kimi bloqueado por orçamento, acesso identificado e desenho independente.",
    75: "Não há resultados pareados nem revisores independentes para análise estatística e revisão cega.",
    76: "Otimização/treino condicionado a ganhos comprovados; não iniciado sem a evidência exigida.",
    80: "Múltiplos hosts condicionados à necessidade medida; nenhuma escala adicional habilitada.",
}


LOCAL_ACCEPTANCE = {
    "AT-007-1": ["test_kill_after_task_commit_resumes_without_repeating_retrieval"],
    "AT-007-2": ["test_acknowledged_tampering_is_never_silently_repaired"],
    "AT-020-1": ["test_distinct_process_commits_do_not_lose_checkpoints"],
    "AT-020-2": ["test_backup_restores_committed_exports_and_keeps_blobs"],
    "AT-021-1": ["test_one_lease_wins"],
    "AT-021-2": ["test_expired_worker_cannot_publish"],
    "AT-022-1": [
        "test_kill_between_blob_write_and_commit_leaves_only_recoverable_orphans"
    ],
    "AT-022-2": ["test_equivalent_output_paths_block_before_scaffolding"],
    "AT-023-1": [
        "test_arbitrary_task_ids_and_additional_registered_capabilities_execute"
    ],
    "AT-023-2": ["test_missing_capability_blocks_planning_before_writing"],
    "AT-032-1": [
        "test_new_validation_preserves_completed_branches_and_original_receipts"
    ],
    "AT-032-2": ["test_two_patches_on_same_base_require_rebase"],
}


def local_acceptance(path: Path) -> dict:
    cases = list(ET.parse(path).getroot().iter("testcase"))
    supplemental = ROOT / "audit/continuation-fencing.xml"
    if supplemental.is_file():
        cases.extend(ET.parse(supplemental).getroot().iter("testcase"))
    observations = {}
    for scenario, names in LOCAL_ACCEPTANCE.items():
        matched = [
            case for case in cases if case.get("name", "").split("[")[0] in names
        ]
        passed = bool(matched) and all(
            not any(
                case.find(tag) is not None for tag in ("failure", "error", "skipped")
            )
            for case in matched
        )
        observations[scenario] = {
            "execution_status": "CENARIO_APROVADO_LOCALMENTE"
            if passed
            else "CENARIO_NAO_APROVADO",
            "executed_tests": [
                f"{case.get('classname')}::{case.get('name')}" for case in matched
            ],
            "junit": path.relative_to(ROOT).as_posix(),
            "supplemental_junit": supplemental.relative_to(ROOT).as_posix()
            if supplemental.is_file()
            else None,
            "scope": "Windows, testes locais; não certifica todos os requisitos da tarefa nem revisão de PR",
        }
    return observations


def junit(path: Path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    failures = sum(c.find("failure") is not None for c in cases)
    errors = sum(c.find("error") is not None for c in cases)
    skipped = sum(c.find("skipped") is not None for c in cases)
    return {
        "tests": len(cases),
        "passed": len(cases) - failures - errors - skipped,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "junit": path.relative_to(ROOT).as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main():
    plan_path = ROOT / ".plano/BACKLOG_KIMISWARM.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    observations = local_acceptance(ROOT / "audit/final-junit.xml")
    rows = []
    for task in plan["tasks"]:
        number = int(task["id"].split("-")[1])
        if number in PROGRESS:
            implemented, remaining, evidence = PROGRESS[number]
            status = "IMPLEMENTACAO_PARCIAL"
            evidence = [evidence]
        else:
            implemented, remaining, evidence = (
                "Sem implementação nova certificada nesta execução.",
                NOT_STARTED[number],
                [],
            )
            status = (
                "CONDICIONAL_NAO_INICIADO"
                if number in {76, 80}
                else "BLOQUEADO_EXTERNO"
                if number in {74, 75}
                else "PENDENTE"
            )
        rows.append(
            {
                "id": task["id"],
                "title": task["title"],
                "priority": task["priority"],
                "depends_on": task["depends_on"],
                "status": status,
                "implemented": implemented,
                "remaining": remaining,
                "evidence": evidence,
                "fully_accepted": False,
                "subtasks": [
                    {
                        **s,
                        "status": "NAO_CERTIFICADA_INTEGRALMENTE",
                        "task_evidence": evidence,
                    }
                    for s in task["subtasks"]
                ],
                "acceptance_tests": [
                    {
                        **a,
                        "execution_status": "CENARIO_COMPLETO_NAO_ATESTADO",
                        "related_evidence": evidence,
                        **observations.get(a["id"], {}),
                    }
                    for a in task["acceptance_tests"]
                ],
            }
        )
    final = junit(ROOT / "audit/final-junit.xml")
    baseline = junit(ROOT / "audit/baseline-junit.xml")
    coverage = json.loads(
        (ROOT / "audit/final-coverage.json").read_text(encoding="utf-8")
    )["totals"]
    validation = {
        "baseline": baseline,
        "current": final,
        "coverage": coverage,
        "python": sys.version,
        "platform": platform.platform(),
        "sqlite": sqlite3.sqlite_version,
        "live_model_calls": 0,
        "kimi_product_evaluations": 0,
        "remote_publication": False,
        "meaning": "Unit/integration tests are not a research-quality or SOTA score.",
        "limits": [
            "Windows only in this session",
            "model CLI fixtures are simulated",
            "host plugin E2E untested",
            "no independent held-out evaluation",
        ],
        "distribution_evidence": "audit/distribution.json",
        "acceptance_observations": observations,
        "lint": {"ruff_version": "0.15.8", "check": "passed", "format": "passed"},
        "governance_evidence": "audit/governance-observation.json",
        "changed_files_evidence": "audit/changed-files.json",
    }
    if (ROOT / "audit/py310-junit.xml").is_file():
        validation["python_310_validation"] = {
            **junit(ROOT / "audit/py310-junit.xml"),
            "environment": json.loads(
                (ROOT / "audit/py310-environment.json").read_text(encoding="utf-8")
            ),
        }
    (ROOT / "audit/validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output = {
        "original_backlog_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "baseline_commit": plan["metadata"]["commit"],
        "checkout_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT)
        .decode()
        .strip(),
        "working_tree_modified": True,
        "plan_fully_completed": False,
        "task_counts": dict(Counter(r["status"] for r in rows)),
        "counts_are_not_readiness": True,
        "acceptance_rule": "Partial implementation or a related passing test does not certify all five subtasks and both scenarios.",
        "tasks": rows,
        "release_gates": [
            {**g, "execution_status": "NAO_CERTIFICADO"} for g in plan["release_gates"]
        ],
    }
    (ROOT / "audit/execution-status.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Registro de execução do plano",
        "",
        "Os três documentos originais foram preservados. Este registro descreve a implementação parcial e suas lacunas; não encerra o backlog.",
        "",
        f"Baseline: {baseline['passed']} testes aprovados. Implementação: {final['passed']} aprovados, {final['failed']} falhos, {final['errors']} erros, {final['skipped']} ignorados.",
        "",
        f"Cenários do backlog aprovados no escopo local e vinculados ao JUnit: {sum(o['execution_status'] == 'CENARIO_APROVADO_LOCALMENTE' for o in observations.values())}. Isso não certifica as tarefas completas nem os gates de release.",
        "",
        "Provedores configuráveis: Codex e Claude Code. Inferências reais nesta execução: zero. Benchmark Kimi: não executado.",
        "",
        "Veja [resultados](../audit/validation.json), [matriz completa com 400 subtarefas e 160 cenários](../audit/execution-status.json), [guia operacional](../docs/EXECUTION.md) e [pacotes verificados](../audit/distribution.json).",
        "",
        "| Tarefa | Estado | Implementação / pendência |",
        "|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['status']} | {row['implemented']} **Falta:** {row['remaining']} |"
        )
    (ROOT / ".plano/EXECUCAO_KIMISWARM.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps({"tests": final, "tasks": output["task_counts"]}, indent=2))


if __name__ == "__main__":
    main()
