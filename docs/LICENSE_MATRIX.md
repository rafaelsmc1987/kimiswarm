# License matrix (plan §46, P0)

How each inspected repository may be used in a **commercial** product, and what
this tree actually does with it.

| Project | License | Reuse in this tree | Notes |
|---|---|---|---|
| Orchestra-Research/AI-Research-SKILLs | MIT | Concepts only (ARA format, provenance, seals, exploration DAG) | Reimplemented clean-room in `kdrx.artifact`, `kdrx.state`. |
| Weizhena/Deep-Research-skills | MIT | Concepts only (`outline.yaml`/`fields.yaml` items-and-fields UX) | Not copied; the R7 route is a spec in the plan, not a port. |
| affaan-m/ECC | MIT | Concepts only (hooks, memory, continuous learning) | Reimplemented in `kdrx.hooks`, `kdrx.security`. |
| Imbad0202/academic-research-skills (ARS) | **CC BY-NC 4.0** | **None** — ideas only, clean-room | No prompt, file or code copied. See `CLEAN_ROOM_RECORD.md`. |
| rafaelsmc1987/kimiswarm | (this repo) | Control plane base | `kdrx` is the new executable layer. |

## Rule applied

- **MIT**: selective reuse allowed with attribution; here we reimplemented to
  keep a single coherent codebase and avoid vendored drift.
- **CC BY-NC 4.0**: no commercial copy of text or code; only independently
  written requirements derived from observation. Documented in
  `CLEAN_ROOM_RECORD.md`.

## Benchmarks considered (non-code references)

DeepResearch Bench II, DeepWeb-Bench, BrowseComp/Plus, SAGE,
MMDeepResearch-Bench, Cross-lingual BrowseComp Plus, Wiki Live Challenge,
DeepResearchGym, S1-DeepResearch, ParallelSearch, RECON, NVIDIA AI-Q,
OpenAI Deep Research. Referenced for metric design only (§36–37); no benchmark
assets are bundled.
