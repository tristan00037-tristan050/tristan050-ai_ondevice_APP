#!/usr/bin/env node
/**
 * 정확도 하한선 게이트
 * 골든셋 개수 및 정확도 임계치 검증
 * 
 * @module gate_accuracy
 */

import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '..');

const MIN_GOLD = Number(process.env.MIN_GOLD ?? 50);
const THRESH_TOP1 = Number(process.env.THRESH_TOP1 ?? 0.70);
const THRESH_TOP5 = Number(process.env.THRESH_TOP5 ?? 0.85);

function run() {
  const scriptPath = path.join(ROOT_DIR, 'scripts/measure_accuracy.js');
  return execFileSync(process.execPath, [
    scriptPath,
    '--gold',
    'datasets/gold/ledgers.json',
    '--top-n',
    '5'
  ], { 
    encoding: 'utf8',
    cwd: ROOT_DIR,
    maxBuffer: 10 * 1024 * 1024
  });
}

function pick(re, out, label) {
  const m = out.match(re);
  if (!m) throw new Error(`parse error: ${label}\n` + out);
  return m.slice(1).map(Number);
}

try {
  const out = run();
  
  const [total] = pick(/총\s*테스트\s*케이스:\s*(\d+)/, out, 'total');
  const [top1Hit, top1All] = pick(/TOP-?1\s*정확도:\s*(\d+)\s*\/\s*(\d+)/i, out, 'top1');
  const [top5Hit, top5All] = pick(/TOP-?5\s*정확도:\s*(\d+)\s*\/\s*(\d+)/i, out, 'top5');
  
  const top1 = top1Hit / top1All;
  const top5 = top5Hit / top5All;
  
  console.log(out.trim());
  console.log(`\nGate: MIN_GOLD=${MIN_GOLD}, TOP1>=${THRESH_TOP1}, TOP5>=${THRESH_TOP5}`);
  console.log(`Measured: total=${total}, TOP1=${(top1 * 100).toFixed(1)}%, TOP5=${(top5 * 100).toFixed(1)}%`);
  
  if (total < MIN_GOLD) throw new Error(`❌ Gold too small: ${total} < ${MIN_GOLD}`);
  if (top1 < THRESH_TOP1) throw new Error(`❌ Top‑1 below: ${(top1 * 100).toFixed(1)}% < ${(THRESH_TOP1 * 100).toFixed(1)}%`);
  if (top5 < THRESH_TOP5) throw new Error(`❌ Top‑5 below: ${(top5 * 100).toFixed(1)}% < ${(THRESH_TOP5 * 100).toFixed(1)}%`);
  
  console.log('✅ Accuracy gate passed');
} catch (e) {
  console.error(String(e?.message ?? e));
  process.exit(1);
}


