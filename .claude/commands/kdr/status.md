---
description: "KDR-X: show run status, DAG progress and gates"
argument-hint: "--run-dir <dir>"
---

# /kdr:status

Report the current state of a run.

## Emit

- run id, route, status and elapsed waves;
- completed / failed / pending task counts;
- the last gate results (`plan`, `source`, `claim`, `citation`, `security`);
- unresolved critical claims and open contradictions;
- any hash mismatch or secret-scan finding.

`python3 -m kdrx.cli status --run-dir <dir>` prints the manifest summary;
append the event log (`events.jsonl`) for the full lifecycle timeline.
