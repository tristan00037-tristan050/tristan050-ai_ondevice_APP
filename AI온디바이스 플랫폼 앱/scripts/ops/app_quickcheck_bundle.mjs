#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync } from 'node:child_process';

function parseArgs() {
  const args = process.argv.slice(2);
  const out = { zip: false };
  for (let i=0;i<args.length;i++) {
    const a = args[i];
    if (a === '--qc') out.qc = args[++i];
    else if (a === '--md') out.md = args[++i];
    else if (a === '--out') out.out = args[++i];
    else if (a === '--base-url') out.baseUrl = args[++i];
    else if (a === '--policy-version') out.policyVersion = args[++i];
    else if (a === '--app-version') out.appVersion = args[++i];
    else if (a === '--zip') out.zip = true;
    else if (a === '--help' || a === '-h') out.help = true;
  }
  return out;
}

const argv = parseArgs();
if (argv.help || !argv.qc || !argv.md || !argv.out) {
  console.error('Usage: node app_quickcheck_bundle.mjs --qc <qc.json> --md <qc.md> --out <outDir> [--base-url URL] [--policy-version v] [--app-version v] [--zip]');
  process.exit(2);
}

fs.mkdirSync(argv.out, { recursive: true });

const copy = (src, dst) => fs.copyFileSync(src, path.join(argv.out, dst));

copy(argv.qc, 'qc.json');
copy(argv.md, 'qc.md');

const meta = {
  generated_at: new Date().toISOString(),
  base_url: argv.baseUrl || null,
  policy_version: argv.policyVersion || null,
  app_version: argv.appVersion || null
};
fs.writeFileSync(path.join(argv.out, 'bundle_meta.json'), JSON.stringify(meta, null, 2));

// checksums
const files = ['qc.json','qc.md','bundle_meta.json'];
const sha256 = (p)=>crypto.createHash('sha256').update(fs.readFileSync(path.join(argv.out,p))).digest('hex');
let csum = '';
for (const f of files) csum += f + '  ' + sha256(f) + '\n';
fs.writeFileSync(path.join(argv.out,'checksums.txt'), csum);

// optional zip via system 'zip' (if available)
if (argv.zip) {
  const zipPath = argv.out + '.zip';
  const res = spawnSync('zip', ['-r', zipPath, path.basename(argv.out)], { cwd: path.dirname(argv.out), stdio: 'inherit' });
  if (res.status !== 0) {
    console.error('[bundle] zip command failed or unavailable. Bundle left as directory.');
  } else {
    console.log('[bundle] zip created at', zipPath);
  }
}
console.log('[bundle] done:', argv.out);