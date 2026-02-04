#!/usr/bin/env node
/**
 * 골든셋 합성 비율 게이트
 * meta.synthetic=true 비율을 점검하여 임계값 초과 시 실패
 * 
 * @module gold_enforce_ratio
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '..');

const FILE = process.env.GOLD_FILE ?? 'datasets/gold/ledgers.json';
const MAX_SYN_RATIO = Number(process.env.MAX_SYN_RATIO ?? 0.30); // 30%

const filePath = path.isAbsolute(FILE) ? FILE : path.join(ROOT_DIR, FILE);
const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));

if (!Array.isArray(data)) {
  console.error('gold file must be an array');
  process.exit(1);
}

const total = data.length;
const syn = data.filter(x => x?.meta?.synthetic === true).length;
const ratio = total === 0 ? 0 : syn / total;

console.log(`gold size=${total}, synthetic=${syn}, ratio=${(ratio * 100).toFixed(1)}% (limit ${(MAX_SYN_RATIO * 100).toFixed(0)}%)`);

if (total === 0) {
  console.error('❌ gold set empty');
  process.exit(1);
}

if (ratio > MAX_SYN_RATIO) {
  console.error(`❌ synthetic ratio too high: ${(ratio * 100).toFixed(1)}% > ${(MAX_SYN_RATIO * 100).toFixed(0)}%`);
  process.exit(1);
}

console.log('✅ synthetic ratio gate passed');


