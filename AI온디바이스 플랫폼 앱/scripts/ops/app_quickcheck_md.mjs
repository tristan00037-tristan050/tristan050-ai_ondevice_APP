#!/usr/bin/env node
import fs from 'node:fs';

const file = process.argv[2];
if (!file) {
  console.error('Usage: node app_quickcheck_md.mjs <qc.json>');
  process.exit(2);
}
const qc = JSON.parse(fs.readFileSync(file,'utf8'));

const stateEmoji = (s) => ({
  pass: '🟢 PASS',
  warn: '🟡 WARN',
  fail: '🔴 FAIL',
  na:   '⚪ N/A'
})[s] || s;

function table(rows) {
  const header = '| Indicator | State |\n|---|---|';
  const body = rows.map(r=>`| ${r.k} | ${r.v} |`).join('\n');
  return [header, body].join('\n');
}

const lines = [];
lines.push(`# QuickCheck Report`);
lines.push('');
lines.push('## Status');
const statusRows = Object.entries(qc.status || {}).map(([k,v])=>({k, v: stateEmoji(v)}));
lines.push(table(statusRows));
lines.push('');

lines.push('## Diff Summary');
const diff = qc.diff?.summary || [];
if (diff.length === 0) {
  lines.push('_N/A_');
} else {
  for (const d of diff.slice(0, 10)) {
    const badge = d.dir === '+' ? '▲' : d.dir === '-' ? '▼' : '=';
    const detail = d.label ?? `${d.id} ${badge} ${d.pct ?? d.delta ?? ''}`.trim();
    lines.push(`- ${badge} ${detail}`);
  }
  if (diff.length > 10) lines.push(`- (+${diff.length-10} more...)`);
}
lines.push('');

lines.push('## Policy Evaluation');
const evals = qc.policy?.evaluations || [];
if (evals.length === 0) {
  lines.push('_N/A_');
} else {
  for (const e of evals.slice(0, 10)) {
    lines.push(`- [${e.severity?.toUpperCase?.() || ''}] ${e.id ?? ''}: ${e.result ?? ''}`);
  }
  if (evals.length > 10) lines.push(`- (+${evals.length-10} more...)`);
}
lines.push('');

lines.push('## Notes');
const notes = qc.notes || [];
if (notes.length === 0) {
  lines.push('_None_');
} else {
  for (const n of notes) lines.push(`- ${n}`);
}
console.log(lines.join('\n'));