#!/usr/bin/env node
// Create an evidence bundle (qc.md + qc.json + bundle_meta.json + checksums.txt [+ zip])
// Usage: node app_quickcheck_bundle.mjs --qc ./qc.json --md ./qc.md --out ./bundle_dir [--zip] --base-url https://internal-gw --policy-version v1 --app-version 1.0.0

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const args = process.argv.slice(2);
const getArg = (k, def) => {
  const i = args.indexOf(k);
  return i===-1 ? def : args[i+1];
};
const has = (k) => args.includes(k);

const qcPath = getArg('--qc', null);
const mdPath = getArg('--md', null);
const outDir = getArg('--out', null);
const baseUrl = getArg('--base-url', '');
const policyVersion = getArg('--policy-version', '');
const appVersion = getArg('--app-version', '');
const doZip = has('--zip');

if(!qcPath || !mdPath || !outDir){
  console.error('Usage: app_quickcheck_bundle.mjs --qc <qc.json> --md <qc.md> --out <dir> [--zip] --base-url <url> --policy-version <v> --app-version <v>');
  process.exit(2);
}

fs.mkdirSync(outDir, {recursive: true});

const qcTarget = path.join(outDir, 'qc.json');
const mdTarget = path.join(outDir, 'qc.md');
fs.copyFileSync(qcPath, qcTarget);
fs.copyFileSync(mdPath, mdTarget);

const meta = {
  generated_at: new Date().toISOString(),
  base_url: baseUrl || undefined,
  policy_version: policyVersion || undefined,
  app_core_version: appVersion || undefined
};
fs.writeFileSync(path.join(outDir, 'bundle_meta.json'), JSON.stringify(meta, null, 2));

function sha256(p){
  const buf = fs.readFileSync(p);
  return crypto.createHash('sha256').update(buf).digest('hex');
}
const files = ['qc.json','qc.md','bundle_meta.json'];
const sums = files.map(f => `${sha256(path.join(outDir,f))}  ${f}`).join('\n') + '\n';
fs.writeFileSync(path.join(outDir, 'checksums.txt'), sums, 'utf8');

if (doZip) {
  const zipName = path.basename(outDir) + '.zip';
  const { spawnSync } = await import('node:child_process');
  // Try zip program if available
  const res = spawnSync('zip', ['-r', zipName, path.basename(outDir)], {cwd: path.dirname(outDir)});
  if (res.status!==0) {
    console.error('zip utility not available; skip creating zip archive.');
  } else {
    console.log('Created zip:', path.join(path.dirname(outDir), zipName));
  }
}

console.log('Bundle created at:', outDir);
