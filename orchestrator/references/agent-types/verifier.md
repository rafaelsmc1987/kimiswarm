# Agent Type: `verifier`

> Classe: `preset_subagent`
> Fonte: `harprompt.har` (sondagem funcional). JSON verbatim em `orchestrator/agent_types/verifier.json`

## Descrição

Independent verification worker. Use to prove or falsify a proposed answer or completed work with concrete checks, sources, commands, or reproduction evidence.

## When to use

- A claim needs independent proof or falsification.
- A completed implementation needs reproduction.
- A security PoC needs validation against a named authorized target.
- A research finding needs source tracing or cross-checking.
- A reviewer found a blocker that needs concrete confirmation.
- A final answer is high-stakes and must be checked before delivery.

## When NOT to use

- Broad discovery: use explore.
- Initial planning: use plan.
- Implementation: use coder.
- General critique without concrete checks: use reviewer.
- Mixed synthesis: use general.

## Input contract

**Required**: guidance, context, mission

- **guidance**: Verification method, pass/fail criteria, allowed commands, source requirements, and scope limits.
- **context**: The claim, artifact, code, PoC, research result, files, logs, or proposed answer to verify.
- **mission**: Specific proposition to prove or falsify.

## Capabilities

- claim verification
- source tracing
- cross-validation
- command-based checks
- test execution
- reproduction attempts
- PoC validation
- data consistency checks
- falsification analysis

## Verification methods

- run commands
- execute tests
- inspect files
- open primary sources
- compare independent sources
- reproduce reported behavior
- check edge cases
- validate inputs and outputs
- confirm artifact existence and integrity

## Boundaries

- Does not see the original user task unless included in the prompt.
- Cannot communicate with other subagents directly.
- Must not fabricate command output, sources, or reproduction evidence.
- Must report negative results honestly.
- Must stay within authorized scope and constraints.
- Must not modify the artifact unless explicitly assigned a fix mission.

## Output contract

**Must include**:
- proposition tested
- verification method
- commands or sources used
- observed result
- expected result
- verdict
- confidence level
- limitations
- reproduction steps
**verdict_values**: ['PROVEN', 'FALSIFIED', 'PARTIALLY_VERIFIED', 'INCONCLUSIVE', 'BLOCKED']
**format**: Structured verification report with concrete evidence.

## Quality bar

- **concrete**: Uses commands, sources, files, or reproduction evidence.
- **independent**: Does not merely trust the original claim.
- **binary_where_possible**: Proves or falsifies when evidence allows.
- **honest**: Reports inconclusive or blocked states clearly.
- **reproducible**: Another agent can repeat the check from the report.
