// kdr-run — execute a persisted ResearchPlan wave by wave (T-02-02/T-02-06).
//
// Waves são uma BARRIERE: cada wave usa pipeline() sobre as tasks para
// concorrência real por item; entre waves há um gate determinístico
// (saídas declaradas existem, sem tasks null). Falhas não viram sucesso:
// resultados null são contados e bloqueiam as waves seguintes em vez de
// deixar dependências correr sem insumos (mesma semântica do WaveScheduler).
//
// Input (global `args`): { run_dir: string, corpus?: string }
// Output: { run_dir, waves, gates, failed, blocking }

export const meta = {
  name: 'kdr-run',
  description:
    'Execute a persisted kdr plan with real concurrency per wave and deterministic gates between waves',
  phases: ['load', 'waves', 'gate', 'stop'],
}

if (
  args === undefined ||
  typeof args !== 'object' ||
  !args ||
  !String(args.run_dir || '').trim()
) {
  return {
    blocking: true,
    error: 'usage: /kdr-x:kdr-run with args = { run_dir, corpus? }',
  }
}

const runDir = String(args.run_dir).trim()
const corpus = args.corpus ? String(args.corpus) : null

// -------------------------------------------------------------------- load --

phase('load')

const LOAD_SCHEMA = {
  type: 'object',
  required: ['run_id', 'tasks'],
  properties: {
    run_id: { type: 'string' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['task_id', 'mission', 'dependencies', 'outputs', 'wave'],
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
  },
}

const loaded = await agent(
  [
    'Read ' + runDir + '/plan.json (use Read). If plan.json is missing, run',
    '`kdr status --run-dir ' + runDir + '` with Bash to confirm and return an EMPTY tasks array.',
    'If manifest.json exists, prefer its run_id. Extract every task with its REAL wave from the',
    'plan; waves were derived from dependencies at compile time — preserve them exactly.',
  ].join('\n'),
  { label: 'kdr-run:load', phase: 'load', schema: LOAD_SCHEMA },
)

if (loaded === null || loaded.tasks.length === 0) {
  return { blocking: true, error: loaded === null ? 'load agent lost (null result)' : 'no tasks in plan.json', run_dir: runDir }
}

const waveNums = Array.from(new Set(loaded.tasks.map((t) => t.wave))).sort((a, b) => a - b)

// ------------------------------------------------------------------- waves --

const TASK_SCHEMA = {
  type: 'object',
  required: ['task_id', 'status', 'outputs_written'],
  properties: {
    task_id: { type: 'string' },
    status: { type: 'string', enum: ['succeeded', 'failed'] },
    outputs_written: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
}

const GATE_SCHEMA = {
  type: 'object',
  required: ['passed', 'missing', 'wave'],
  properties: {
    passed: { type: 'boolean' },
    missing: { type: 'array', items: { type: 'string' } },
    wave: { type: 'integer' },
  },
}

const waves = []
const gates = []
const failed = []
let blocking = false

for (const w of waveNums) {
  if (blocking) break
  phase('waves')

  const waveTasks = loaded.tasks.filter((t) => t.wave === w)

  // pipeline(): concorrência real por task, DENTRO da wave (tasks da mesma
  // wave não dependem entre si — invariante do compile_dag/SAME_WAVE_DEP).
  const results = await pipeline(waveTasks, async (t) => {
    const r = await agent(
      [
        'Execute task ' + t.task_id + ' of kdr run ' + loaded.run_id + '.',
        'Mission: ' + t.mission,
        (corpus ? 'Corpus path: ' + corpus + '.' : ''),
        'Declared outputs (write EVERY one under ' + runDir + ', non-empty): ' +
          JSON.stringify(t.outputs),
        'After writing, run `kdr status --run-dir ' + runDir + '` with Bash to confirm scaffolding.',
        'status=succeeded only if every declared output exists and is non-empty.',
      ].join('\n'),
      { label: 'kdr-run:' + t.task_id, phase: 'waves', schema: TASK_SCHEMA },
    )
    // T-02-06: null do runtime = perda determinística da task, nunca sucesso
    if (r === null) {
      return { task_id: t.task_id, status: 'failed', outputs_written: [], error: 'null agent result' }
    }
    return r
  })

  const waveResults = results.filter(Boolean)
  const waveFailed = waveResults.filter((r) => r.status !== 'succeeded')
  failed.push(...waveFailed.map((r) => r.task_id))
  waves.push({ wave: w, tasks: waveResults })

  // ---------------------------- gate entre waves (T-02-06) ----------------------------
  phase('gate')
  const expectedOutputs = waveTasks.flatMap((t) => t.outputs)
  const gate = await agent(
    [
      'Wave ' + w + ' gate for kdr run ' + loaded.run_id + '.',
      'For EACH of these declared outputs, confirm the file exists under ' + runDir +
        ' and is non-empty (use Read):',
      JSON.stringify(expectedOutputs),
      'Also run `kdr status --run-dir ' + runDir + '` with Bash and confirm no failed tasks.',
      'passed=true only if ALL outputs exist, are non-empty, and no task failed in the wave.',
    ].join('\n'),
    { label: 'kdr-run:gate:w' + w, phase: 'gate', schema: GATE_SCHEMA },
  )

  const gateResult =
    gate === null
      ? { passed: false, missing: expectedOutputs, wave: w, error: 'null gate agent result' }
      : gate
  if (waveFailed.length > 0) gateResult.passed = false
  gates.push(gateResult)

  if (!gateResult.passed) {
    blocking = true // waves seguintes NÃO rodam sem os insumos desta wave
  }
}

phase('stop')

// Gate de stop do harness (kdr-hook) resume/recheca isto; aqui só reportamos.
return {
  blocking,
  run_dir: runDir,
  run_id: loaded.run_id,
  waves,
  gates,
  failed,
  next: blocking
    ? 'fix failed wave outputs, then `kdr resume`'
    : 'run `/kdr-x:kdr-verify { run_dir: "' + runDir + '" }` before delivery',
}
