// kdr-deep-research — E2E plan -> run -> verify >report (T-02-04).
//
// Compõe a orquestração inteira num script: council fan-out -> synthesis ->
// waves com gates -> verification adversarial -> delivery. Scripts de
// workflow são standalone por constraint do runtime (module loading é
// rejeitado antes do run); o DNA estrutural é o mesmo de
// kdr-plan/kdr-run/kdr-verify.
//
// Input (global `args`):
//   args = "<objective>"  |  { objective, corpus?, out?, run_dir? }
// Se args.run_dir existir e tiver plan.json, pula a fase de plan (resume do checkpoint).
// Output: { blocking, run_dir, report, verdict, summary }

export const meta = {
  name: 'kdr-deep-research',
  description: 'Full deep-research pipeline: planner council -> gated waves -> adversarial verify -> cited report delivery',
  phases: ['plan', 'council', 'synthesize', 'waves', 'verify', 'report'],
}

if (
  args === undefined ||
  (typeof args === 'string' && !args.trim()) ||
  (typeof args === 'object' && !String((args && args.objective) || '').trim())
) {
  return { blocking: true, error: 'usage: /kdr-x:kdr-deep-research "<objective>" | { objective, corpus?, out?, run_dir? }' }
}

const objective = typeof args === 'string' ? args.trim() : String(args.objective).trim()
const corpus = typeof args === 'object' && args.corpus ? String(args.corpus) : null
const outRoot = typeof args === 'object' && args.out ? String(args.out) : '.research'
const resumeRunDir = typeof args === 'object' && args.run_dir ? String(args.run_dir) : null

// --------------------------------------------------------------------- plan --

phase('plan')

const SCAFFOLD_SCHEMA = {
  type: 'object',
  required: ['run_dir', 'contract', 'plan_ref'],
  properties: {
    run_dir: { type: 'string' },
    contract: { type: 'string' },
    plan_ref: { type: 'string', description: 'path to plan.json persisted' },
  },
}

const scaffold = await agent(
  [
    resumeRunDir
      ? 'Resume mode: confirm ' + resumeRunDir + '/plan.json exists (Read it briefly).'
      : 'Create the deterministic run scaffold: Bash `kdr plan --objective "' +
        objective.replace(/"/g, "'") +
        '"' +
        (corpus ? ' --corpus ' + corpus : '') +
        ' --out ' +
        outRoot +
        ' --json`.',
    'Return the run_dir (from the JSON), a one-line contract summary, and the plan.json path.',
  ].join('\n'),
  { label: 'kdr-dr:plan', phase: 'plan', schema: SCAFFOLD_SCHEMA },
)

if (scaffold === null) {
  return { blocking: true, error: 'plan agent lost (null result)' }
}
const runDir = resumeRunDir || scaffold.run_dir

// ------------------------------------------------------------------ council --

phase('council')

const PERSPECTIVES = ['requirements', 'scope', 'retrieval', 'methodology', 'risk']
const COUNCIL_SCHEMA = {
  type: 'object',
  required: ['perspective', 'key_queries_or_checks'],
  properties: {
    perspective: { type: 'string' },
    key_queries_or_checks: { type: 'array', items: { type: 'string' } },
  },
}

const council = (
  await parallel(
    PERSPECTIVES.map((p) =>
      agent(
        [
          'KDR-X planner council, perspective "' + p + '", objective: ' + objective,
          corpus ? 'Local corpus: ' + corpus : 'Search the web for primary sources.',
          'Return 3-5 concrete queries/checks this research MUST perform for your perspective.',
        ].join('\n'),
        { label: 'dr:council:' + p, phase: 'council', schema: COUNCIL_SCHEMA },
      ),
    ),
  )
).filter(Boolean)

if (council.length !== PERSPECTIVES.length) {
  return { blocking: true, error: 'council incomplete', run_dir: runDir, received: council.length }
}
const councilHints = council.flatMap((c) => c.key_queries_or_checks)

// --------------------------------------------------------------- synthesize --

phase('synthesize')

const SYN_SCHEMA = {
  type: 'object',
  required: ['waves'],
  properties: {
    waves: {
      type: 'array',
      items: {
        type: 'array',
        items: {
          type: 'object',
          required: ['task_id', 'mission', 'outputs'],
          properties: {
            task_id: { type: 'string' },
            mission: { type: 'string' },
            outputs: { type: 'array', items: { type: 'string' } },
          },
        },
      },
    },
  },
}

const synth = await agent(
  [
    'Read ' + runDir + '/plan.json (Read) — that is the deterministic Python scaffold DAG',
    '(intake/retrieve/verify/synthesize/integrity; T-VERIFY already depends on T-RETRIEVE).',
    'Enrich each task mission with the council hints below (queries to run, checks to enforce),',
    'keeping the SAME task ids, waves and dependencies. Do NOT add dependencies in the same wave.',
    '',
    JSON.stringify(councilHints),
  ].join('\n'),
  { label: 'dr:synthesize', phase: 'synthesize', schema: SYN_SCHEMA },
)

if (synth === null) {
  return { blocking: true, error: 'synthesizer lost (null result)', run_dir: runDir }
}

// ------------------------------------------------------------------- waves --

const TASK_SCHEMA = {
  type: 'object',
  required: ['task_id', 'status'],
  properties: {
    task_id: { type: 'string' },
    status: { type: 'string', enum: ['succeeded', 'failed'] },
    note: { type: 'string' },
  },
}

const wavesReport = []
let blocking = false

for (let w = 0; w < synth.waves.length; w++) {
  if (blocking) break
  phase('waves')

  const results = (
    await pipeline(synth.waves[w], (t) =>
      agent(
        [
          'KDR-X run ' + runDir + ', task ' + t.task_id + ':',
          t.mission,
          'Write every declared output under ' + runDir + ' (non-empty): ' + JSON.stringify(t.outputs),
          'If you cannot produce an output, return status=failed with the reason — never fake it.',
        ].join('\n'),
        { label: 'dr:' + t.task_id, phase: 'waves', schema: TASK_SCHEMA },
      ),
    )
  ).map((r, i) => r || { task_id: synth.waves[w][i].task_id, status: 'failed', note: 'null agent result' })

  const waveFailed = results.filter((r) => r.status !== 'succeeded').map((r) => r.task_id)
  wavesReport.push({ wave: w, results, failed: waveFailed })
  if (waveFailed.length > 0) blocking = true // T-02-06: gate entre waves
}

if (blocking) {
  return { blocking, run_dir: runDir, waves: wavesReport, error: 'wave gate failed; run `kdr resume --run-dir ' + runDir + '`' }
}

// ------------------------------------------------------------------- verify --

phase('verify')

const VERIFY_SCHEMA = {
  type: 'object',
  required: ['verdict', 'unverified'],
  properties: {
    verdict: { type: 'string', enum: ['pass', 'fail', 'unverifiable'] },
    unverified: { type: 'array', items: { type: 'string' } },
  },
}

const verify = await agent(
  [
    'Run the verification gates via Bash: `kdr verify --run-dir ' + runDir + '`.',
    'Then read verification/integrity.json + verification/security.json and the claims/standings.',
    'verdict=pass only if every gate JSON says "pass". Unreadable/missing => unverifiable, and list',
    'what could not be checked — unverifiable NEVER counts as a pass and never as a refutation.',
  ].join('\n'),
  { label: 'dr:verify', phase: 'verify', schema: VERIFY_SCHEMA },
)

const verdict = verify === null ? 'unverifiable' : verify.verdict
const unverified = verify === null ? ['all (null agent result)'] : verify.unverified

// ------------------------------------------------------------------- report --

phase('report')

const REPORT_SCHEMA = {
  type: 'object',
  required: ['report_path', 'summary'],
  properties: {
    report_path: { type: 'string' },
    summary: { type: 'string' },
  },
}

const report = await agent(
  [
    'Write ' + runDir + '/delivery/report.md (Write): objective, method, top claims with citations',
    'from claims/claims.jsonl + evidence/spans.jsonl, verification verdict "' + verdict + '", and',
    'an explicit "Unresolved/Unverified" section for: ' + JSON.stringify(unverified) + '.',
    'Citations reference source ids from corpus/sources.jsonl. Return the path and a 3-line summary.',
  ].join('\n'),
  { label: 'dr:report', phase: 'report', schema: REPORT_SCHEMA },
)

if (report === null) {
  return { blocking: true, run_dir: runDir, error: 'report agent lost (null result)', verdict }
}

return {
  blocking: verdict !== 'pass',
  run_dir: runDir,
  report: report.report_path,
  summary: report.summary,
  verdict,
  unverified,
  council: council.map((c) => c.perspective),
  waves: wavesReport.map((w) => ({ wave: w.wave, failed: w.failed })),
  next: 'audit with `kdr verify --run-dir ' + runDir + '` and deliver via `/kdr-x:report`',
}
