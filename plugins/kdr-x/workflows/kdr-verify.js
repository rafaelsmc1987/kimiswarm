// kdr-verify — verification as a gate demo (T-02-03).
//
// Fan-out adversarial: source-verifier + devils-advocate reconferem o run, e
// um final-integrity-auditor consolida. Uma claim que não pôde ser checada é
// "unverifiable" — nunca conta como refutada nem como suportada (mesma regra
// do /deep-research embutido). O verdict final é FAIL se qualquer gate real
// não passar.
//
// Input (global `args`): { run_dir: string }
// Output: { run_dir, verdict, checks, unverified, blocking }

export const meta = {
  name: 'kdr-verify',
  description:
    'Adversarial verification gate over a kdr run: source trust, citation integrity, security — null-safe',
  phases: ['verify', 'consolidate'],
}

if (args === undefined || typeof args !== 'object' || !args || !String(args.run_dir || '').trim()) {
  return { blocking: true, error: 'usage: /kdr-x:kdr-verify with args = { run_dir }', verdict: 'fail' }
}

const runDir = String(args.run_dir).trim()

const CHECK_SCHEMA = {
  type: 'object',
  required: ['gate', 'verdict', 'details'],
  properties: {
    gate: { type: 'string' },
    verdict: { type: 'string', enum: ['pass', 'fail', 'warn', 'unverifiable'] },
    details: { type: 'string' },
  },
}

phase('verify')

const checks = (
  await parallel([
    agent(
      [
        'You are the source-verifier (agents/source-verifier.md). Run `kdr verify --run-dir ' +
          runDir +
          '` with Bash,',
        'read verification/integrity.json and verification/security.json, and report the SOURCE-TRUST',
        'dimension: did every cited source resolve and grade? If `kdr verify` cannot run, report',
        'verdict=unverifiable — do NOT guess.',
      ].join('\n'),
      { label: 'verify:source-trust', phase: 'verify', schema: CHECK_SCHEMA },
    ),
    agent(
      [
        'You are the devils-advocate (agents/devils-advocate.md). Read ' +
          runDir +
          '/claims/claims.jsonl and',
        runDir + '/claims/standings.jsonl. Report the FALSIFICATION dimension: any CRITICAL/MAJOR claim',
        'left UNRESOLVED or SUPPORTED-without-evidence-span fails the gate. If artifacts are missing',
        'or unreadable, report verdict=unverifiable.',
      ].join('\n'),
      { label: 'verify:falsification', phase: 'verify', schema: CHECK_SCHEMA },
    ),
    agent(
      [
        'You are the final-integrity-auditor (agents/final-integrity-auditor.md). Read ' +
          runDir +
          '/verification/security.json and confirm the SECURITY dimension: no secrets, no egress,',
        'no path escapes, artifacts sealed. If security.json is missing, run',
        '`kdr verify --run-dir ' + runDir + '` with Bash first. Missing after that => verdict=fail.',
      ].join('\n'),
      { label: 'verify:security', phase: 'verify', schema: CHECK_SCHEMA },
    ),
  ])
).filter(Boolean)

phase('consolidate')

// Deterministic consolidation (audit B-04: unverifiable never counts as pass)
const allPassed = checks.length === 3 && checks.every((c) => c.verdict === 'pass')
const anyUnverifiable = checks.length < 3 || checks.some((c) => c.verdict === 'unverifiable')
const verdict = allPassed ? 'pass' : anyUnverifiable ? 'unverifiable' : 'fail'

return {
  run_dir: runDir,
  verdict,
  checks,
  unverified: checks.filter((c) => c.verdict === 'unverifiable').map((c) => c.gate),
  blocking: verdict !== 'pass',
}
