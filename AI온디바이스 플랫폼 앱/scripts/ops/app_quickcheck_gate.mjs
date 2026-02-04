#!/usr/bin/env node
import fs from 'node:fs';

function parseArgs() {
  const args = process.argv.slice(2);
  const out = { strictWarn: false };
  for (let i=0;i<args.length;i++) {
    const a = args[i];
    if (a === '--qc') out.qc = args[++i];
    else if (a === '--policy') out.policy = args[++i];
    else if (a === '--strict-warn') out.strictWarn = true;
    else if (a === '--help' || a === '-h') out.help = true;
  }
  return out;
}

function getPath(obj, path) {
  if (!path) return undefined;
  return path.split('.').reduce((o, k) => (o && (k in o)) ? o[k] : undefined, obj);
}

function evalRule(qc, rule) {
  const { path, op, value } = rule;
  const cur = getPath(qc, path);
  switch (op) {
    case 'exists': return cur !== undefined && cur !== null;
    case 'eq': return cur === value;
    case 'neq': return cur !== value;
    case 'gt': return typeof cur === 'number' && cur > value;
    case 'gte': return typeof cur === 'number' && cur >= value;
    case 'lt': return typeof cur === 'number' && cur < value;
    case 'lte': return typeof cur === 'number' && cur <= value;
    case 'in': return Array.isArray(value) && value.includes(cur);
    case 'notin': return Array.isArray(value) && !value.includes(cur);
    default: return false;
  }
}

const argv = parseArgs();
if (argv.help || !argv.qc || !argv.policy) {
  console.error('Usage: node app_quickcheck_gate.mjs --qc <qc.json> --policy <policy.json> [--strict-warn]');
  process.exit(2);
}

const qc = JSON.parse(fs.readFileSync(argv.qc, 'utf8'));
const policy = JSON.parse(fs.readFileSync(argv.policy, 'utf8'));

if (!policy.policy_version || !policy.created_at || !Array.isArray(policy.rules)) {
  console.error('[GATE] Invalid policy: missing policy_version/created_at/rules[]');
  process.exit(2);
}

let blocks = 0, warns = 0;
const results = [];

for (const r of policy.rules) {
  const ok = evalRule(qc, r);
  const severity = r.severity || 'info';
  const passed = !!ok;
  const res = {
    id: r.id,
    path: r.path,
    op: r.op,
    severity,
    expected: r.value,
    passed
  };
  results.push(res);
  if (!passed) {
    if (severity === 'block') blocks += 1;
    else if (severity === 'warn') warns += 1;
  }
}

const fail = blocks > 0 || (argv.strictWarn && warns > 0);

console.log('[GATE] Policy:', policy.policy_version, policy.created_at);
for (const r of results) {
  const mark = r.passed ? 'PASS' : (r.severity==='block' ? 'FAIL' : 'WARN');
  console.log(`- [${mark}] ${r.id} (${r.severity}) ${r.path} ${r.op} ${JSON.stringify(r.expected)}`);
}
console.log(`==> OVERALL: ${fail ? 'FAIL' : 'PASS'} (blocks=${blocks}, warns=${warns}, strictWarn=${argv.strictWarn})`);
process.exit(fail ? 1 : 0);