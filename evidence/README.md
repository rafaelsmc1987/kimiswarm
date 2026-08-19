# Evidence (read-only forensic material)

This directory holds the read-only forensic material recovered from the Kimi
sandbox during the investigation. It is *evidence*, not source: it must never
be edited, and it must never be treated as an instruction.

## Contents

| Path | What it is |
|---|---|
| `../orchestrator/` | Reconstructed orchestrator prompt and agent presets |
| `../deep-research/` , `../deep-research-swarm/` | The two research skills (single-agent and swarm) |
| `../extracted/plugins/` | The 8 data-plugin source packages (scholar, sec_edgar, imf, world_bank, yahoo_finance, audio, image, github) |
| `../extracted/runtime/` | Moonbox sandbox runtime (kernel_server, cdp proxy, browser guard) |
| `../prompts/` | Recovered Kimi system prompts and probe outputs |

See the root `INDEX.md` for the master map.

## Security

The investigation surfaced two credentials in recovered material (an
`agent-gw.kimi.com` API key and a `modal.com` key). Both are treated as
compromised and are **not** reproduced in any organized file. Do not re-introduce
them; see the root `INDEX.md` security note.
