# KDR-X — KimiSwarm Deep Research eXtended

A claim-evidence operating system for state-of-the-art deep research, built as
an executable layer on top of the Kimi Swarm control-plane design. This package
implements the deterministic core of the architecture specified in
[`Plano/PLANO_SOTA_SUPER_DEEP_RESEARCH.md`](../Plano/PLANO_SOTA_SUPER_DEEP_RESEARCH.md).

> A central scheduler produces an adaptive DAG; specialized agents collect,
> verify, falsify, analyze and write; every claim is tied to exact evidence;
> every stage passes deterministic and independent gates.

## What this is

KDR-X replaces "count searches" with **verifiable claim coverage**. The MVP
(plan §43) is fully implemented and tested offline:

1. Kimi plan / DAG / waves — `kdrx.dag`, `kdrx.scheduler`, `kdrx.planner`
2. research contract — `kdrx.schemas.ResearchContract`
3. hybrid retrieval (BM25 + file corpus) — `kdrx.retrieval`
4. `SourceRecord` — `kdrx.schemas.corpus` / `kdrx.corpus`
5. `EvidenceSpan` — `kdrx.schemas.corpus`
6. atomic `Claim` — `kdrx.claims`
7. supports/contradicts edges — `kdrx.schemas.claims`
8. source verifier — `kdrx.verification`
9. counterevidence verifier — `kdrx.verification`
10. claim standing — `kdrx.claims.compute_standing`
11. evidence packs — `kdrx.reporting`
12. report pipeline — `kdrx.reporting`, `kdrx.runner`
13. claim/citation integrity gate — `kdrx.reporting.citation_integrity_gate`
14. eval harness — `kdrx.evals`

## Package layout

```
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
kdr hook pre_tool_use --json '{"tool_name":"Write","tool_input":{"file_path":"../x"}}'
```

Claude Code surface: `/kdr:plan`, `/kdr:run`, `/kdr:resume`, `/kdr:status`,
`/kdr:verify`, `/kdr:report`, `/kdr:monitor`, `/kdr:doctor`, `/kdr:eval`
(`.claude/commands/kdr/`).

## Guarantees (Definition of Done, plan §44)

- Every complex run creates a plan before searching.
- Every task has schema, owner, dependencies and acceptance.
- No dependent runs in the same wave.
- Every material claim resolves to an exact evidence span.
- Every source has a canonical identity; dependent sources do not count as
  independent.
- Every critical contradiction is investigated; every claim gets a standing
  and a confidence basis.
- Writers never do central research; reviewers are independent.
- Citations exist *and* entail the claim; calculations are reproducible.
- The final delivery requires an integrity pass and a clean secret scan.
- Hooks block violations deterministically.

## License / provenance

This is a clean-room, MIT-licensed implementation of the requirements described
in `Plano/`. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md),
[`LICENSE_MATRIX.md`](LICENSE_MATRIX.md) and
[`CLEAN_ROOM_RECORD.md`](CLEAN_ROOM_RECORD.md). No ARS (CC BY-NC 4.0) text or
code was copied into this tree.
