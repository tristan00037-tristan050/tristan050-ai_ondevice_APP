#!/usr/bin/env node
/**
 * 합성 케이스를 실제/수작업 케이스로 치환
 * 합성 비율을 목표 비율로 조정
 * 
 * @module swap_synthetic
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '..');

const FILE = process.env.GOLD_FILE ?? 'datasets/gold/ledgers.json';
const TARGET_RATIO = Number(process.env.TARGET_SYN_RATIO ?? 0.30); // 30%
const REAL_FILE = process.env.REAL_FILE ?? 'datasets/real/ledgers_real.json'; // 실제/수작업 케이스 샘플 파일

const filePath = path.isAbsolute(FILE) ? FILE : path.join(ROOT_DIR, FILE);
const realFilePath = path.isAbsolute(REAL_FILE) ? REAL_FILE : path.join(ROOT_DIR, REAL_FILE);

const gold = JSON.parse(fs.readFileSync(filePath, 'utf8'));
const real = fs.existsSync(realFilePath) ? JSON.parse(fs.readFileSync(realFilePath, 'utf8')) : [];

const synIdx = gold.map((x, i) => [x?.meta?.synthetic === true, i]).filter(([b]) => b).map(([, i]) => i);
const curSyn = synIdx.length;
const total = gold.length;
const curRatio = total ? curSyn / total : 0;

console.log(`gold=${total}, synthetic=${curSyn} (${(curRatio * 100).toFixed(1)}%)`);

if (!total) {
  console.log('gold set empty');
  process.exit(0);
}

if (curRatio <= TARGET_RATIO) {
  console.log('✅ already ≤ target');
  process.exit(0);
}

if (!Array.isArray(real) || real.length === 0) {
  console.error('❌ no real set');
  process.exit(2);
}

let need = Math.ceil(curSyn - TARGET_RATIO * total);
let ri = 0;
let replaced = 0;

for (const idx of synIdx) {
  if (need <= 0) break;
  
  const sample = real[ri % real.length];
  ri++;
  
  // 실제 케이스로 교체 (필수 필드만 보존/맵핑)
  gold[idx] = {
    ...sample,
    meta: { ...(sample.meta ?? {}), synthetic: false }
  };
  
  need--;
  replaced++;
}

fs.writeFileSync(filePath, JSON.stringify(gold, null, 2) + '\n', 'utf8');
console.log(`✅ replaced synthetic → real: ${replaced} rows (target ${(TARGET_RATIO * 100).toFixed(0)}%)`);


