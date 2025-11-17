#!/usr/bin/env node
// Evaluate a QuickCheck JSON snapshot against a policy and set exit code accordingly.
// Usage: node app_quickcheck_gate.mjs --qc ./qc.json --policy ./policy.json [--strict-warn]

import fs from 'node:fs';

const args = process.argv.slice(2);
const getArg = (k, def) => {
  const i = args.indexOf(k);
  if (i===-1) return def;
  return args[i+1];
};
const has = (k) => args.includes(k);

const qcPath = getArg('--qc', null);
const policyPath = getArg('--policy', null);
const strictWarn = has('--strict-warn');

if (!qcPath || !policyPath) {
  console.error('Usage: app_quickcheck_gate.mjs --qc <qc.json> --policy <policy.json> [--strict-warn]');
  process.exit(2);
}

const qc = JSON.parse(fs.readFileSync(qcPath, 'utf8'));
const policy = JSON.parse(fs.readFileSync(policyPath, 'utf8'));

let blocks = 0, warns = 0;
let evaluations = policy.rules?.map(r => ({
  rule_id: r.id,
  target: r.target,
  severity: r.severity,
  verdict: 'pass'
})) ?? [];

// Minimal demo evaluator for a subset of operators.
function valueForTarget(qc, target){
  if (target==='jwks') return qc?.raw?.jwks?.status ?? qc?.status?.jwks;
  if (target==='lighthouse') return qc?.raw?.lighthouse?.staleness_hours ?? null;
  if (target==='holidays') return qc?.raw?.holidays?.provider_state ?? null;
  if (target==='api') return qc?.status?.api;
  if (target==='ics') return qc?.raw?.ics ?? null;
  if (target==='observability') return qc?.raw?.observability ?? null;
  return null;
}

for (const e of evaluations) {
  const rule = policy.rules.find(x=>x.id===e.rule_id);
  const val = valueForTarget(qc, rule.target);
  let hit = false;

  switch(rule.operator){
    case 'eq': hit = (val===rule.value); break;
    case 'neq': hit = (val!==rule.value); break;
    case 'stale_hours_gt': hit = (typeof val==='number' && val>rule.value); break;
    case 'exists':
      if (rule.value==='primary_or_fallback') {
        hit = !!(val?.primary_available || val?.fallback_available);
      } else {
        hit = (val!=null);
      }
      break;
    default: hit = false;
  }

  if (hit) {
    e.verdict = rule.severity;
    if (rule.severity==='block') blocks++;
    else if (rule.severity==='warn') warns++;
  } else {
    e.verdict = 'pass';
  }
}

const fail = blocks>0 || (strictWarn && warns>0);
if (fail) {
  console.error(`[QC GATE] FAIL: blocks=${blocks} warns=${warns} (strict=${strictWarn})`);
  process.exit(1);
}
console.log(`[QC GATE] PASS: blocks=${blocks} warns=${warns} (strict=${strictWarn})`);
process.exit(0);
