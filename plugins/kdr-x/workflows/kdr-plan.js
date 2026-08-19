// kdr-plan — planner council workflow (plan §14, audit T-02-01).
//
// Fan-out real dos 5 planners (requirements, scope, retrieval, methodology,
// risk) + reviewer + verifier + synthesizer. A orquestração vive NESTE
// script (não turno-a-turno). Agente agents/planner-council.md é a referência
// textual das perspectivas; Python (kdr CLI) fica restrito a
// schemas/state/gates (fronteira T-02-08): o synthesizer persiste o plano e
// um agente de validação roda `kdr doctor` + validações determinísticas.
//
// Input (global `args`):
//   args = { objective: string, corpus?: string, out?: string }
//   ou args = "<objective>"
// Output: { run_dir, plan, council, review, verification, blocking }

export const meta = {
  name: 'kdr-plan',
  description:
    'Planner council fan-out: 5 perspectives -> review -> adversarial verify -> plan synthesis with deterministic gates',
  phases: ['council', 'review', 'verify', 'synthesize', 'gate'],
}

if (
  args === undefined ||
  (typeof args !== 'object' && typeof args !== 'string') ||
  (typeof args === 'string' && !args.trim()) ||
  (typeof args === 'object' && (!args || !String(args.objective || '').trim()))
) {
  return {
    blocking: true,
    error: 'usage: /kdr-x:kdr-plan with args = "<objective>" | { objective, corpus?, out? }',
  }
}

const objective = typeof args === 'string' ? args.trim() : String(args.objective).trim()
const corpus = typeof args === 'object' && args.corpus ? String(args.corpus) : null
const outRoot = typeof args === 'object' && args.out ? String(args.out) : '.research'

// ---------------------------------------------------------------- schemas --

const PERSPECTIVE_SCHEMA = {
  type: 'object',
  required: ['perspective', 'summary', 'recommendations', 'tasks'],
  properties: {
    perspective: { type: 'string' },
    summary: { type: 'string', description: 'key findings for this perspective' },
    recommendations: { type: 'array', items: { type: 'string' } },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['task_id', 'mission', 'outputs'],
        properties: {
          task_id: { type: 'string' },
          mission: { type: 'string' },
          dependencies: { type: 'array', items: { type: 'string' } },
          outputs: { type: 'array', items: { type: 'string' } },
          critical: { type: 'boolean' },
        },
      },
      description: 'candidate TaskSpecs (compact form)',
    },
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['approved', 'issues', 'merged_summary'],
  properties: {
    approved: { type: 'boolean' },
    issues: { type: 'array', items: { type: 'string' } },
    merged_summary: { type: 'string' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  required: ['passed', 'critical_issues'],
  properties: {
    passed: { type: 'boolean' },
    critical_issues: { type: 'array', items: { type: 'string' } },
  },
}

const PLAN_SCHEMA = {
  type: 'object',
  required: ['plan_id', 'objective', 'plan_md', 'tasks'],
  properties: {
    plan_id: { type: 'string' },
    objective: { type: 'string' },
    plan_md: { type: 'string', description: 'human-readable plan.md content' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['task_id', 'mission', 'dependencies', 'outputs'],
        properties: {
          task_id: { type: 'string' },
          mission: { type: 'string' },
          dependencies: { type: 'array', items: { type: 'string' } },
          outputs: { type: 'array', items: { type: 'string' } },
          wave: { type: 'integer' },
          critical: { type: 'boolean' },
        },
      },
    },
    run_manifest: { type: 'object', description: 'optional run scaffold metadata' },
  },
}

// ---------------------------------------------------------------- council --

phase('council')

const PERSPECTIVES = [
  {
    id: 'requirements',
    brief: 'decision context, audience, success metrics, output format',
  },
  {
    id: 'scope',
    brief: 'the research question, in/out of scope boundaries, exclusions',
  },
  {
    id: 'retrieval',
    brief:
      'query graph: definition, primary-source, entity, quantitative, controversy, counterevidence, temporal, local-language queries (plan §18)',
  },
  {
    id: 'methodology',
    brief: 'route selection (R0-R12), evidence hierarchy, stopping criterion, analytical compute',
  },
  {
    id: 'risk',
    brief: 'falsification criteria, integrity gates, HITL tiers, secret/egress guardrails',
  },
]

function plannerPrompt(p) {
  return [
    'You are the KDR-X "' + p.id + '" planner of the planner council (plan §14).',
    'Focus: ' + p.brief + '.',
    'Objective: ' + objective + (corpus ? '\nCorpus available at: ' + corpus : ''),
    'Produce ONLY recommendations and candidate tasks for your perspective.',
    'Hard DAG invariants every candidate task must respect:',
    '- one mission per task; outputs are repo-relative paths;',
    '- dependencies must be explicit (waves are derived, never a substitute);',
    '- critical tasks require an independent reviewer;',
    '- read-only research workers must never hold destructive tools.',
  ].join('\n')
}

const council = (
  await parallel(
    PERSPECTIVES.map((p) => agent(plannerPrompt(p), { label: 'planner:' + p.id, phase: 'council', schema: PERSPECTIVE_SCHEMA })),
  )
).filter(Boolean)

if (council.length !== PERSPECTIVES.length) {
  // T-02-06: perda de planner é falha determinística, não plano degradado
  // silencioso. null do runtime = agente parado/erro irrecuperável.
  return {
    blocking: true,
    error: 'planner council incomplete',
    expected: PERSPECTIVES.length,
    received: council.length,
    missing: PERSPECTIVES.map((p) => p.id).filter((id) => !council.some((c) => c.perspective === id)),
  }
}

// ----------------------------------------------------------------- review --

phase('review')

const review = await agent(
  [
    'You are the KDR-X planner REVIEWER. Reconcile the five planner-perspective outputs below into',
    'one coherent planning position. Flag every conflict, gap or redundancy as an issue.',
    'Approve ONLY if the merged position is coherent and actionable.',
    '',
    JSON.stringify(council, null, 2),
  ].join('\n'),
  { label: 'council:review', phase: 'review', schema: REVIEW_SCHEMA },
)

if (review === null) {
  return { blocking: true, error: 'reviewer agent lost (null result)', council }
}

// ----------------------------------------------------------------- verify --

phase('verify')

const verification = await agent(
  [
    'You are the KDR-X plan VERIFIER (devils-advocate, plan §14/§29). Adversarially check the',
    'merged plan position below against the objective. Reject if: a critical claim lacks a',
    'verifier, a read-only task holds destructive tools, dependencies would be cyclic, or the',
    'scope is not falsifiable. Be strict; ambiguity fails.',
    '',
    'Objective: ' + objective,
    '',
    'Merged position: ' + review.merged_summary,
    'Issues from reviewer: ' + JSON.stringify(review.issues),
  ].join('\n'),
  { label: 'council:verify', phase: 'verify', schema: VERIFY_SCHEMA },
)

if (verification === null) {
  return { blocking: true, error: 'verifier agent lost (null result)', council, review }
}
if (!verification.passed) {
  return {
    blocking: true,
    error: 'plan council verification failed',
    critical_issues: verification.critical_issues,
    council,
    review,
  }
}

// ------------------------------------------------------------- synthesize --

phase('synthesize')

const synthesis = await agent(
  [
    'You are the KDR-X planner SYNTHESIZER. Turn the approved council output below into the final',
    'ResearchPlan for objective "' + objective + '".',
    'Rules:',
    '- run scaffold directory: ' + outRoot + ' (the runtime persists your final plan.json/plan.md);',
    '- dependencies explicit; waves are derived FROM dependencies — set the wave field consistently',
    '  with them (wave(task) > wave(dep) for every dep);',
    '- T-RETRIEVE/verify style races are forbidden: a task that consumes an output must declare',
    '  the producing task as a dependency;',
    '- keep the plan small but complete: intake -> retrieval -> verification -> synthesis -> integrity;',
    '- use the Bash tool ONLY to create the run scaffold with `kdr plan --objective "' +
      objective.replace(/"/g, "'") +
      '" --out ' +
      outRoot +
      ' --json` (deterministic Python scaffold) and read its plan.json as the structural reference;',
    '- then return the FINAL plan as structured output (do not just copy the scaffold: merge the',
    '  council tasks in; every task needs explicit dependencies).',
    '',
    'Approved merged position: ' + review.merged_summary,
    'Council tasks: ' + JSON.stringify(council.flatMap((c) => c.tasks)),
  ].join('\n'),
  { label: 'council:synthesize', phase: 'synthesize', schema: PLAN_SCHEMA },
)

if (synthesis === null) {
  return { blocking: true, error: 'synthesizer agent lost (null result)', council, review }
}

// -------------------------------------------------------------------- gate --

phase('gate')

// Plan gate estrutural: invariants deriváveis em JS puro (espelho de
// kdrx.dag.compile_dag); o demo E2E roda o gate real via `kdr verify`.
const planIssues = []
const taskIds = new Set(synthesis.tasks.map((t) => t.task_id))
if (taskIds.size !== synthesis.tasks.length) planIssues.push('DUP_ID')
for (const t of synthesis.tasks) {
  for (const dep of t.dependencies || []) {
    if (!taskIds.has(dep)) planIssues.push('UNRESOLVED_DEP: ' + t.task_id + ' -> ' + dep)
  }
  // waves derivadas: nenhum dep na mesma wave ou posterior
  if (typeof t.wave === 'number') {
    for (const dep of t.dependencies || []) {
      const d = synthesis.tasks.find((x) => x.task_id === dep)
      if (d && typeof d.wave === 'number' && d.wave >= t.wave) {
        planIssues.push('SAME_WAVE_DEP: ' + t.task_id + ' -> ' + dep)
      }
    }
  }
  if (!String(t.mission || '').trim()) planIssues.push('NO_MISSION: ' + t.task_id)
}

if (planIssues.length > 0) {
  return { blocking: true, error: 'structural plan gate failed', plan_issues: planIssues, plan: synthesis }
}

return {
  blocking: false,
  run_root: outRoot,
  plan: synthesis,
  council: council.map((c) => c.perspective),
  review: { approved: review.approved, issues: review.issues },
  verification,
  note:
    'E2E demo gate: apos synthesize, rode `/kdr-x:kdr-run` (com run_dir) ou `kdr run --run-dir ...` para executar com gates reais entre waves.',
}
