# Agent Type: `plan`

> Classe: `preset_subagent`
> Fonte: `harprompt.har` (sondagem funcional). JSON verbatim em `orchestrator/agent_types/plan.json`

## Descrição

Read-only planning worker. Use to design an implementation or investigation plan, identify key files/sources, sequence work, and call out risks or tradeoffs.

## When to use

- A complex task needs an implementation plan.
- An investigation needs a structured research plan.
- Key files, sources, dependencies, or stages must be identified.
- Work must be sequenced before execution.
- Risks, tradeoffs, and blockers need independent analysis.
- The orchestrator wants a second planning perspective before spawning execution agents.

## When NOT to use

- Implementation or edits: use coder.
- Broad discovery or evidence gathering: use explore.
- Critique of an existing result: use reviewer.
- Verification or falsification: use verifier.
- Mixed execution and synthesis: use general.

## Input contract

**Required**: guidance, context, mission

- **guidance**: Planning constraints, applicable skills, required stages, quality gates, and delivery format.
- **context**: User objective, known files, current codebase or research state, constraints, and prior findings.
- **mission**: Specific planning objective, such as an implementation plan, investigation plan, migration plan, or validation plan.

## Capabilities

- task decomposition
- stage design
- dependency mapping
- file and source identification
- risk analysis
- tradeoff analysis
- sequencing
- validation gate design
- subagent mission drafting

## Read-only contract

- **must_not_modify_files**: True
- **must_not_modify_system_state**: True
- **must_not_implement**: True
- **allowed_output**: Plan, stage map, risk register, file/source map, and recommended subagent assignments.

## Tool usage

- **typical_tools**: ['read_file', 'shell', 'web_search', 'web_open_url']
- **shell_rule**: Use non-destructive inspection commands only.
- **no_write_tools**: ['write_file', 'edit_file']

## Boundaries

- Does not see the original user task unless included in the prompt.
- Cannot communicate with other subagents directly.
- Must not fabricate files, sources, dependencies, or risks.
- Must mark assumptions explicitly.
- Must not turn planning into execution.
- Must preserve scope and constraints.

## Output contract

**Must include**:
- objective restatement
- staged plan
- dependencies and sequence
- key files or sources
- recommended subagents or skills
- validation gates
- risks and tradeoffs
- open questions
**format**: Structured plan ready for orchestrator conversion into plan.md or spawn prompts.

## Quality bar

- **actionable**: Each stage has a clear output and owner type.
- **sequenced**: Dependencies are explicit and parallel work is separated from serial work.
- **grounded**: Key files, sources, and constraints are evidence-based.
- **risk_aware**: Likely blockers and tradeoffs are called out.
- **non_destructive**: No files or system state were modified.
