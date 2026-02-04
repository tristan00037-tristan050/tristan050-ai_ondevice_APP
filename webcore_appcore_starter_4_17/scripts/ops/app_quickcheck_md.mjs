#!/usr/bin/env node
// Format a QuickCheck JSON snapshot as Markdown (App-side).
// Usage: node app_quickcheck_md.mjs ./qc.json > qc.md

import fs from 'node:fs';

function emoji(state){ return state==='pass'?'🟢':state==='warn'?'🟡':state==='fail'?'🔴':'⚪'; }

const input = process.argv[2];
if(!input){ console.error('Usage: app_quickcheck_md.mjs <qc.json>'); process.exit(2); }
const qc = JSON.parse(fs.readFileSync(input, 'utf8'));

let md = [];
md.push('# QuickCheck Report');
md.push('');
md.push('## Status');
md.push('| Indicator | State |');
md.push('|---|---|');
for (const k of ['api','jwks','holidays','observability','ics','lighthouse']) {
  const s = qc.status?.[k] ?? 'na';
  md.push(`| ${k} | ${emoji(s)} ${s.toUpperCase()} |`);
}
md.push('');

if (qc.diff?.summary?.length) {
  md.push('## Diff Summary (Top)');
  for (const d of qc.diff.summary) {
    md.push(`- ${d.id}: ${d.trend} (${d.deltaPct}%)`);
  }
  md.push('');
}

if (qc.policy) {
  md.push('## Policy Evaluation');
  if (qc.policy.policy_version) md.push(`- policy_version: ${qc.policy.policy_version}`);
  if (qc.policy.created_at) md.push(`- created_at: ${qc.policy.created_at}`);
  if (qc.policy.evaluations?.length) {
    md.push('');
    md.push('| Rule | Target | Verdict | Severity |');
    md.push('|---|---|---|---|');
    for (const e of qc.policy.evaluations) {
      md.push(`| ${e.rule_id} | ${e.target} | ${e.verdict} | ${e.severity} |`);
    }
  }
  md.push('');
}

if (qc.notes?.length) {
  md.push('## Notes');
  for (const n of qc.notes) md.push(`- ${n}`);
  md.push('');
}

process.stdout.write(md.join('\n'));
