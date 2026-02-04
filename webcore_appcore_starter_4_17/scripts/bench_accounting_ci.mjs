#!/usr/bin/env node
/**
 * 정확도 CI 게이트 스크립트
 * 골든셋 기반 정확도 측정 및 임계치 검증
 * 
 * @module bench_accounting_ci
 */

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const GOLD = process.env.GOLD || 'datasets/gold/ledgers.json';
const TOPN = process.env.TOPN || '5';
const THRESH_TOP1 = parseFloat(process.env.THRESH_TOP1 || '70'); // %
const THRESH_TOP5 = parseFloat(process.env.THRESH_TOP5 || '85'); // %

function runMeasure() {
  return new Promise((resolve, reject) => {
    const args = ['scripts/measure_accuracy.js', '--gold', GOLD, '--top-n', String(TOPN)];
    execFile('node', args, { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }, (err, stdout, stderr) => {
      if (err) return reject(new Error(stderr || err.message));
      resolve(stdout);
    });
  });
}

function pickPct(re, text, label) {
  const m = re.exec(text);
  if (!m) throw new Error(`Failed to parse ${label} from measure output`);
  return parseFloat(m[1]);
}

const reTop1 = /TOP-1\s*정확도:\s*\d+\/\d+\s*\(([\d.]+)%\)/i;
const reTop5 = /TOP-5\s*정확도:\s*\d+\/\d+\s*\(([\d.]+)%\)/i;

try {
  const out = await runMeasure();
  const top1 = pickPct(reTop1, out, 'TOP-1');
  const top5 = pickPct(reTop5, out, 'TOP-5');

  console.log(out.trim());
  console.log(`\nCI Gate — thresholds: TOP-1>=${THRESH_TOP1}%, TOP-5>=${THRESH_TOP5}%`);
  console.log(`Measured — TOP-1=${top1}%, TOP-5=${top5}%`);

  if (Number.isNaN(top1) || Number.isNaN(top5)) {
    console.error('Accuracy parse error.');
    process.exit(1);
  }
  if (top1 < THRESH_TOP1 || top5 < THRESH_TOP5) {
    console.error('❌ Accuracy thresholds not met.');
    process.exit(1);
  }
  console.log('✅ Accuracy thresholds satisfied.');
} catch (e) {
  console.error(e.message || e);
  process.exit(1);
}


