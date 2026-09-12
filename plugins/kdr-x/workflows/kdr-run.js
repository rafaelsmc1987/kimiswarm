// Kernel facade. Agent output is presentation only; native Stop rechecks the store.
export const meta = {
  name: 'kdr-run',
  description: 'Submit a versioned request to the canonical KDR kernel; live capabilities require configured providers',
  phases: ['request', 'receipt'],
}

if (args === undefined || args === null || !['object', 'string'].includes(typeof args)) {
  return { blocking: true, error: 'Provide objective/corpus or run_id/runs_root.' }
}
const input = typeof args === 'string' ? { objective: args } : args
const runDir = input.run_dir ? String(input.run_dir) : undefined
const separator = runDir ? Math.max(runDir.lastIndexOf('/'), runDir.lastIndexOf('\\')) : -1
const root = input.runs_root || input.out || (separator >= 0 ? runDir.slice(0, separator) : '.research/runs')
const request = {
  schema_version: '0.3', operation: 'run', runs_root: root,
  objective: input.objective, corpus: input.corpus,
  run_dir: runDir, run_id: input.run_id,
  backend: input.backend || "offline", model_config_options: input.model_config_options,
}
// UTF-8 and base64 are computed in plain JavaScript. Only this ASCII token
// reaches the command string; user text never becomes shell syntax.
const bytes = []
for (const char of encodeURIComponent(JSON.stringify(request)).match(/%[0-9A-F]{2}|./g)) {
  bytes.push(char[0] === '%' ? parseInt(char.slice(1), 16) : char.charCodeAt(0))
}
const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
let encoded = ''
for (let i = 0; i < bytes.length; i += 3) {
  const value = (bytes[i] << 16) | ((bytes[i + 1] || 0) << 8) | (bytes[i + 2] || 0)
  encoded += alphabet[(value >>> 18) & 63] + alphabet[(value >>> 12) & 63]
  encoded += i + 1 < bytes.length ? alphabet[(value >>> 6) & 63] : '='
  encoded += i + 2 < bytes.length ? alphabet[value & 63] : '='
}
phase('request')
const observation = await agent(
  'Run this exact kernel command with Bash and report its stdout/stderr. Do not create or edit run artifacts. ' +
  'The kernel owns planning, task execution, validation and state. Command: kdr request --payload-base64 ' + encoded,
  { label: 'kdr-run:kernel-request', phase: 'request' },
)
phase('receipt')
if (observation === null) {
  return { blocking: true, error: 'Host agent unavailable; inspect kernel state before retrying.' }
}
return {
  authoritative: false,
  verification_required: true,
  observation,
  next: 'Use kdr status and kdr verify-delivery for the run. Native Stop checks kernel artifacts; agent prose does not approve delivery.',
}
