# KDR-X — KimiSwarm Deep Research eXtended

A claim-evidence operating system for state-of-the-art deep research, built as an
executable layer on top of the Kimi Swarm control-plane design.

> A central scheduler produces an adaptive DAG; specialized agents collect,
> verify, falsify, analyze and write; every claim is tied to exact evidence;
> every stage passes deterministic and independent gates.

## Status (2026-08-19)

A **fundação offline/determinística** está implementada e testada (70 testes,
`pytest tests/`). Uma auditoria independente classificou a fundação em ~68% e o
plano completo em 35.3%: schemas, DAG compiler, primitives de corpus/claims, BM25,
gates básicos e eval harness existem; swarm paralelo real, plugin instalável,
retrieval web, verificação viva de fontes e CI estão em correção (roadmap de 11
PRs — ver `auditoria/` e o plano de correção do projeto).

Esta árvore contém **apenas o produto**. O corpus forense que originou a pesquisa
vive em storage privado separado; `evidence-manifest/` é o índice sanitizado
(paths + SHA256, sem bytes sensíveis).

## O que está implementado

1. Kimi plan / DAG / waves — `kdrx.dag`, `kdrx.scheduler`, `kdrx.planner`
2. Research contract — `kdrx.schemas.ResearchContract`
3. Hybrid retrieval (BM25 + file corpus) — `kdrx.retrieval`
4. `SourceRecord` — `kdrx.schemas.corpus` / `kdrx.corpus`
5. `EvidenceSpan` — `kdrx.schemas.corpus`
6. Atomic `Claim` — `kdrx.claims`
7. Supports/contradicts edges — `kdrx.schemas.claims`
8. Source verifier — `kdrx.verification`
9. Counterevidence verifier — `kdrx.verification`
10. Claim standing — `kdrx.claims.compute_standing`
11. Evidence packs — `kdrx.reporting`
12. Report pipeline — `kdrx.reporting`, `kdrx.runner`
13. Claim/citation integrity gate — `kdrx.reporting.citation_integrity_gate`
14. Eval harness — `kdrx.evals`

## Package layout

```text
src/kdrx/
├── schemas/        # 15 canonical Pydantic models + JSON-Schema export
├── dag.py          # DAG compiler + topological waves + validation
├── scheduler.py    # deterministic wave scheduler, retry, no-progress
├── planner.py      # plan gate
├── state.py        # run dirs, manifest, events, hashing, resume
├── corpus.py       # canonicalization, dedup, independence families
├── retrieval.py    # BM25, file corpus, query graph, stopping criterion
├── claims.py       # decomposition, standing, calibration, independence
├── verification.py # source trust, injection boundary, contradiction
├── analysis.py     # reproducible calculation ledger
├── reporting.py    # evidence packs, citation/integrity gate, assembler
├── artifact.py     # exploration tree, decisions, seals
├── security.py     # path/symlink/secret/egress guards, security gate
├── evals.py        # seeded-defect harness
├── hooks.py        # deterministic PreToolUse / Stop / SubagentStop gates
├── runner.py       # end-to-end offline pipeline (routes R3/R4)
└── cli.py          # `kdr` CLI
```

## Usage

```bash
pip install -e .            # install (pydantic>=2.5)
kdr doctor                  # self-check
kdr eval                    # seeded-defect regression suite
kdr schema --out DIR        # export the 15 canonical JSON schemas
kdr demo --corpus DIR --objective "..." --out .research   # offline run
```

Claude Code surface: `/kdr:plan`, `/kdr:run`, `/kdr:resume`, `/kdr:status`,
`/kdr:verify`, `/kdr:report`, `/kdr:monitor`, `/kdr:doctor`, `/kdr:eval`
(`.claude/commands/kdr/`). Plugin package: `plugins/kdr-x/` — commands, agents,
skills, hooks determinísticos (exit 0/2) e **workflows dinâmicos**
(`workflows/kdr-plan.js`, `kdr-run.js`, `kdr-verify.js`, `kdr-deep-research.js`,
Claude Code ≥ v2.1.154: `agent()`/`pipeline()` com fan-out real; Python mantém
schemas/state/gates).

## Documentação

- `docs/KDRX_README.md` — detalhes do pacote e garantias
- `docs/CLEAN_ROOM_RECORD.md` — registro clean-room
- `docs/LICENSE_MATRIX.md` — matriz de licenças
- `docs/THIRD_PARTY_NOTICES.md` — notas de terceiros
- `SECURITY.md` — política de segurança e reporte de vulnerabilidades

## License / provenance

MIT — escopo definido em `LICENSE`: cobre `src/kdrx/`, `plugins/kdr-x/`, `tests/`,
`docs/`, `.claude/` e configs raiz. Material forense/de terceiros **não** faz parte
deste repositório. Implementação clean-room; nenhum texto/código ARS (CC BY-NC 4.0)
foi copiado para esta árvore.
