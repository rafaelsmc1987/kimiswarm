// kdr-plan — planner council workflow (plan §14, audit T-02-01).
//
// Fan-out real dos 5 planners (requirements, scope, retrieval, methodology,
// risk) + reviewer + verifier + synthesizer. A orquestração vive NESTE
// script (não turno-a-turno). Agente agents/planner-council.md é a referência
// textual das perspectivas; Python (kdr CLI) fica restrito a
// schemas/state/gates (fronteira T-02-08): o scaffold determinístico roda via
// `kdr plan --objective-file` e o plano final passa pelo gate canônico
// `kdr import-plan` (validate-then-write), que persiste plan.json/plan.md.
//
// Input (global `args`):
//   args = { objective: string, corpus?: string, out?: string }
//   ou args = "<objective>"
// Output: { run_dir, plan_hash, revision, plan, council, review, verification, dispositions, note, blocking }

export const meta = {
  name: 'kdr-plan',
  description:
    'Planner council fan-out: scaffold -> 5 perspectives -> review -> adversarial verify -> plan synthesis -> canonical import',
  phases: ['scaffold', 'council', 'review', 'verify', 'synthesize', 'gate', 'import'],
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
const MAX_REPAIRS = 2

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

const SCAFFOLD_SCHEMA = {
  type: 'object',
  required: ['run_dir', 'plan_id', 'contract_id', 'route'],
  properties: {
    run_dir: { type: 'string' },
    plan_id: { type: 'string' },
    contract_id: { type: 'string' },
    route: { type: 'string' },
  },
}

// PLAN_SCHEMA: versão flattened (sem $defs/$ref; enums inline) do
// ResearchPlan.schema.json + TaskSpec.schema.json canônicos (D2). O schema JS
// é shaping/DX; a validação pydantic do `kdr import-plan` é a autoridade final
// (extra="forbid" — nada inválido persiste).
const PLAN_SCHEMA = {
  type: 'object',
  required: ['plan_id', 'contract_id', 'route', 'plan_md', 'tasks'],
  properties: {
    plan_id: { type: 'string' },
    contract_id: { type: 'string' },
    route: { type: 'string' },
    plan_md: { type: 'string', description: 'human-readable plan.md content' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['task_id', 'stage', 'wave', 'role', 'mission', 'dependencies', 'outputs'],
        properties: {
          task_id: { type: 'string' },
          stage: {
            type: 'string',
            enum: [
              'intake',
              'planning',
              'retrieval',
              'verification',
              'analysis',
              'synthesis',
              'writing',
              'review',
              'delivery',
            ],
          },
          wave: { type: 'integer' },
          role: {
            type: 'string',
            enum: [
              'intake_analyst',
              'requirements_analyst',
              'rq_formulator',
              'methodology_architect',
              'dimension_mapper',
              'retrieval_strategist',
              'risk_planner',
              'dag_reviewer',
              'dag_verifier',
              'web_explorer',
              'primary_source_finder',
              'academic_searcher',
              'official_docs_searcher',
              'code_explorer',
              'dataset_finder',
              'news_searcher',
              'local_language_searcher',
              'multimodal_finder',
              'archive_researcher',
              'source_resolver',
              'metadata_verifier',
              'retraction_checker',
              'venue_verifier',
              'evidence_span_extractor',
              'table_figure_extractor',
              'entity_resolver',
              'deduplicator',
              'citation_context_verifier',
              'data_verifier',
              'claim_decomposer',
              'contradiction_analyst',
              'counterevidence_researcher',
              'alternative_hypothesis_analyst',
              'causal_reasoning_analyst',
              'statistical_analyst',
              'comparative_analyst',
              'gap_analyst',
              'uncertainty_calibrator',
              'synthesis_agent',
              'insight_extractor',
              'outline_architect',
              'section_writer',
              'table_figure_designer',
              'section_reviewer',
              'transition_editor',
              'executive_synthesis_writer',
              'citation_manager',
              'report_assembler',
              'artifact_converter',
              'devils_advocate',
              'methodology_reviewer',
              'source_verifier',
              'claim_verifier',
              'calculation_verifier',
              'prompt_injection_auditor',
              'final_integrity_auditor',
            ],
          },
          mission: { type: 'string' },
          dependencies: { type: 'array', items: { type: 'string' } },
          inputs: { type: 'array', items: { type: 'string' } },
          outputs: { type: 'array', items: { type: 'string' } },
          skills: { type: 'array', items: { type: 'string' } },
          tools: { type: 'array', items: { type: 'string' } },
          read_only: { type: 'boolean' },
          source_policy: { type: ['string', 'null'] },
          acceptance: {
            type: 'object',
            properties: {
              criteria: { type: 'array', items: { type: 'string' } },
              output_schema: { type: ['string', 'null'] },
              required_evidence_refs: { type: 'integer' },
            },
          },
          retry_policy: {
            type: 'object',
            properties: {
              max_retries: { type: 'integer' },
              backoff_seconds: { type: 'number' },
              require_alternative_agent: { type: 'boolean' },
            },
          },
          budget: {
            type: 'object',
            properties: {
              tokens: { type: 'integer' },
              queries: { type: 'integer' },
              wall_seconds: { type: 'integer' },
            },
          },
          criticality: { type: 'string', enum: ['high', 'medium', 'low'] },
          status: {
            type: 'string',
            enum: [
              'pending',
              'ready',
              'running',
              'succeeded',
              'failed',
              'retrying',
              'skipped',
              'blocked',
              'cancelled',
            ],
          },
          owner: { type: ['string', 'null'] },
          reviewer: { type: ['string', 'null'] },
          guidance: { type: 'string' },
          metadata: { type: 'object', description: 'free-form per-task context (e.g. context.hints)' },
        },
      },
    },
    waves: {
      type: 'object',
      description: 'wave -> task ids (re-derivado no import; informativo aqui)',
      additionalProperties: { type: 'array', items: { type: 'string' } },
    },
    ownership: {
      type: 'array',
      items: {
        type: 'object',
        required: ['output', 'owner_task_id', 'owner_role'],
        properties: {
          output: { type: 'string' },
          owner_task_id: { type: 'string' },
          owner_role: { type: 'string' },
        },
      },
    },
    budget: {
      type: 'object',
      properties: {
        tokens: { type: 'integer' },
        queries: { type: 'integer' },
        wall_seconds: { type: 'integer' },
      },
    },
    acceptance_matrix: {
      type: 'object',
      additionalProperties: { type: 'array', items: { type: 'string' } },
    },
    created_at: { type: ['string', 'null'] },
  },
}

// SYNTHESIS_SCHEMA: wrapper do structured output do synthesizer (D5).
// ResearchPlan é extra="forbid" — dispositions NÃO podem entrar no plan;
// por isso vivem aqui, lado a lado, e são persistidas separadamente pelo
// import (`--dispositions-file`).
const SYNTHESIS_SCHEMA = {
  type: 'object',
  required: ['plan', 'dispositions'],
  properties: {
    plan: PLAN_SCHEMA,
    dispositions: {
      type: 'array',
      items: {
        type: 'object',
        required: ['recommendation', 'perspective', 'disposition', 'rationale'],
        properties: {
          recommendation: { type: 'string' },
          perspective: { type: 'string' },
          disposition: { type: 'string', enum: ['accepted', 'rejected', 'deferred'] },
          rationale: { type: 'string' },
        },
      },
    },
  },
}

const IMPORT_SCHEMA = {
  type: 'object',
  required: ['plan_hash', 'run_dir', 'status', 'revision'],
  properties: {
    plan_hash: { type: 'string', description: 'sha256 do stdout do import-plan (nunca inventar)' },
    run_dir: { type: 'string' },
    status: { type: 'string', enum: ['ok', 'failed'] },
    revision: { type: 'integer' },
    stderr: { type: 'string' },
  },
}

// ---------------------------------------------------------------- scaffold --

phase('scaffold')

const objectiveFile = outRoot + '/.kdr-objective.txt'

const scaffold = await agent(
  [
    'You are the KDR-X scaffold runner. Create the deterministic run scaffold (D6: the',
    'objective NEVER goes through the shell — it is written to a file and passed via',
    '--objective-file).',
    'Step 0 — ensure the directory ' + outRoot + ' exists (create it if missing).',
    'Step 1 — Write (tool Write) the research objective below to ' + objectiveFile + ',',
    'UTF-8, verbatim, no surrounding quotes or commentary:',
    '',
    objective,
    '',
    'Step 2 — run via Bash: kdr plan --objective-file "' + objectiveFile + '" --out "' + outRoot + '" --json',
    'Return run_dir, plan_id, contract_id and route exactly as printed in the JSON stdout.',
  ].join('\n'),
  { label: 'kdr-plan:scaffold', phase: 'scaffold', schema: SCAFFOLD_SCHEMA },
)

if (scaffold === null) {
  return { blocking: true, error: 'scaffold agent lost (null result)' }
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

let review = await agent(
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

// D3: review.approved é gate obrigatório com loop de repair limitado.
let repairs = 0
while (!review.approved && repairs < MAX_REPAIRS) {
  repairs++
  review = await agent(
    [
      'You are the KDR-X planner REVIEWER (repair pass ' + repairs + ' of ' + MAX_REPAIRS + ').',
      'The previous review was NOT approved. Address EVERY issue below and produce a revised',
      'merged position that resolves them.',
      '',
      'Issues to fix: ' + JSON.stringify(review.issues),
      '',
      JSON.stringify(council, null, 2),
    ].join('\n'),
    { label: 'council:repair:' + repairs, phase: 'review', schema: REVIEW_SCHEMA },
  )
  if (review === null) {
    return { blocking: true, error: 'repair agent lost (null result)', council }
  }
}

if (!review.approved) {
  return {
    blocking: true,
    error: 'council review not approved after ' + repairs + ' repair(s)',
    issues: review.issues,
    council,
  }
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
    'You are the KDR-X planner SYNTHESIZER. Turn the approved council position below into the',
    'final canonical ResearchPlan for objective "' + objective + '".',
    'Identity (copy VERBATIM from the scaffold — never invent or modify):',
    '- plan_id: ' + scaffold.plan_id,
    '- contract_id: ' + scaffold.contract_id,
    '- route: ' + scaffold.route,
    'Rules:',
    '- every task carries stage + role: stage follows the pipeline order (intake -> planning ->',
    '  retrieval -> verification -> analysis -> synthesis -> writing -> review -> delivery) and',
    '  role must be one of the AgentRole enum values (e.g. retrieval_strategist for retrieval,',
    '  source_verifier for source checks, dag_verifier/dag_reviewer for DAG checks,',
    '  devils_advocate/final_integrity_auditor for adversarial checks);',
    '- dependencies explicit: a task that consumes an output MUST declare the producing task as',
    '  a dependency (no same-wave consumer of a producer);',
    '- set task.wave consistently with dependencies, but note: waves are RE-DERIVED by the',
    '  canonical import (`kdr import-plan`) from dependencies — dependency correctness is what',
    '  matters; the wave field is overwritten deterministically on import;',
    '- keep the plan small but complete: intake -> retrieval -> verification -> synthesis -> integrity;',
    '- per-task extra context (queries, checks, hints from the council) goes into task',
    '  metadata.context, not into free-form prose outside the schema;',
    '- ownership: for every declared output, exactly one owner task; critical tasks get an',
    '  independent reviewer (reviewer != owner);',
    '- plan_md: human-readable markdown of the plan including a short disposition summary;',
    '- dispositions: ONE entry per council recommendation with disposition',
    '  accepted/rejected/deferred and a one-line rationale (the import persists them for audit).',
    '',
    'Approved merged position: ' + review.merged_summary,
    'Council tasks: ' + JSON.stringify(council.flatMap((c) => c.tasks)),
  ].join('\n'),
  { label: 'council:synthesize', phase: 'synthesize', schema: SYNTHESIS_SCHEMA },
)

if (synthesis === null) {
  return { blocking: true, error: 'synthesizer agent lost (null result)', council, review }
}

// -------------------------------------------------------------------- gate --

phase('gate')

// Plan gate estrutural: invariants deriváveis em JS puro — pré-validação
// não-autoritativa; o gate real é `kdr import-plan` (compile_dag + plan_gate
// no runtime Python, validate-then-write).
const planIssues = []
const taskIds = new Set(synthesis.plan.tasks.map((t) => t.task_id))
if (taskIds.size !== synthesis.plan.tasks.length) planIssues.push('DUP_ID')
for (const t of synthesis.plan.tasks) {
  for (const dep of t.dependencies || []) {
    if (!taskIds.has(dep)) planIssues.push('UNRESOLVED_DEP: ' + t.task_id + ' -> ' + dep)
  }
  // waves derivadas: nenhum dep na mesma wave ou posterior
  if (typeof t.wave === 'number') {
    for (const dep of t.dependencies || []) {
      const d = synthesis.plan.tasks.find((x) => x.task_id === dep)
      if (d && typeof d.wave === 'number' && d.wave >= t.wave) {
        planIssues.push('SAME_WAVE_DEP: ' + t.task_id + ' -> ' + dep)
      }
    }
  }
  if (!String(t.mission || '').trim()) planIssues.push('NO_MISSION: ' + t.task_id)
}

if (planIssues.length > 0) {
  return { blocking: true, error: 'structural plan gate failed', plan_issues: planIssues, plan: synthesis.plan }
}

// ------------------------------------------------------------------ import --

phase('import')

const importRunDir = scaffold.run_dir

const imported = await agent(
  [
    'You are the KDR-X IMPORT runner. Persist the synthesized plan through the canonical gate',
    '(`kdr import-plan`, validate-then-write).',
    'Step 1 — Write (tool Write) the EXACT plan JSON below, verbatim, to ' +
      importRunDir +
      '/.import/plan.json:',
    JSON.stringify(synthesis.plan, null, 2),
    'Step 2 — Write the EXACT dispositions JSON below, verbatim, to ' +
      importRunDir +
      '/.import/dispositions.json:',
    JSON.stringify(synthesis.dispositions, null, 2),
    'Step 3 — run via Bash: kdr import-plan --run-dir "' +
      importRunDir +
      '" --file "' +
      importRunDir +
      '/.import/plan.json" --dispositions-file "' +
      importRunDir +
      '/.import/dispositions.json" --source council-imported --review-approved --json',
    'If the command exits 0 and the JSON stdout contains plan_hash, return status="ok" with',
    'plan_hash, run_dir and revision exactly as printed (never invent a plan_hash). If the',
    'command exits non-zero, return status="failed" with plan_hash="" and stderr = the error',
    'output verbatim.',
  ].join('\n'),
  { label: 'council:import', phase: 'import', schema: IMPORT_SCHEMA },
)

if (imported === null) {
  return {
    blocking: true,
    error: 'import agent lost (null result)',
    council,
    review: { approved: review.approved, issues: review.issues, repairs },
    verification,
  }
}
if (imported.status !== 'ok' || !imported.plan_hash) {
  return {
    blocking: true,
    error: 'canonical import failed (kdr import-plan)',
    stderr: imported.stderr || '',
    plan: synthesis.plan,
    council,
    review: { approved: review.approved, issues: review.issues, repairs },
    verification,
  }
}

return {
  blocking: false,
  run_dir: scaffold.run_dir,
  plan_hash: imported.plan_hash,
  revision: imported.revision,
  plan: synthesis.plan,
  council: council.map((c) => c.perspective),
  review: { approved: review.approved, issues: review.issues, repairs },
  verification,
  dispositions: synthesis.dispositions.length,
  note:
    'import canonico concluido (`kdr import-plan`): rode `/kdr-x:kdr-run` (com run_dir) ou `kdr run --run-dir ...` para executar com gates reais entre waves.',
}
