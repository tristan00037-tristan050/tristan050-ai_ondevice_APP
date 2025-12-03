#!/usr/bin/env node
/**
 * 골든셋 확장 스크립트
 * 기존 골든셋을 합성 케이스로 안전하게 확장 (PII 없이)
 * 
 * @module augment_golden_set
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '..');

const FILE = process.env.GOLD_FILE ?? 'datasets/gold/ledgers.json';
const MIN = Number(process.env.MIN_GOLD ?? 50);

const vendorTokens = [
  'MERCHANT_CAFE_A', 'MERCHANT_CAFE_B', 'MERCHANT_MEAL_A', 'MERCHANT_TELCO_A',
  'MERCHANT_RENT_A', 'MERCHANT_GAS_A', 'MERCHANT_INS_A', 'MERCHANT_TAX_A',
  'MERCHANT_FEE_A', 'MERCHANT_SUPPLY_A'
];

const tags = ['[전자영수증]', '[카드승인]', '[현금영수증]', '[간이영수증]'];

function readJson(p) { return JSON.parse(fs.readFileSync(p, 'utf8')); }
function writeJson(p, data) { fs.writeFileSync(p, JSON.stringify(data, null, 2) + '\n', 'utf8'); }

function mutateDesc(s) {
  const tag = tags[Math.floor(Math.random() * tags.length)];
  const v = vendorTokens[Math.floor(Math.random() * vendorTokens.length)];
  return `${s ?? ''} ${tag} - ${v}`;
}

function cloneCase(c) {
  const out = structuredClone(c);
  
  // input.line_items: desc/description 둘 다 케이스 지원
  if (out?.input?.line_items && Array.isArray(out.input.line_items)) {
    out.input.line_items = out.input.line_items.map(li => {
      const ni = { ...li };
      if (ni.desc) ni.desc = mutateDesc(ni.desc);
      if (ni.description) ni.description = mutateDesc(ni.description);
      // 금액/통화는 그대로 유지하여 ground_truth와 모순 방지
      return ni;
    });
  } else if (out?.entries && Array.isArray(out.entries)) {
    // 기존 포맷 (entries 기반) - note 필드만 보강
    out.entries = out.entries.map(e => ({
      ...e,
      note: e.note ? mutateDesc(e.note) : e.note,
    }));
  }
  
  // synthetic 플래그 추가
  out.meta = { ...(out.meta ?? {}), synthetic: true };
  
  // id 재생성 (중복 방지)
  if (out.id) {
    out.id = `${out.id}_synth_${Date.now()}_${Math.random().toString(36).substring(7)}`;
  }
  
  return out;
}

const filePath = path.isAbsolute(FILE) ? FILE : path.join(ROOT_DIR, FILE);
const data = readJson(filePath);

if (!Array.isArray(data)) {
  console.error('gold file must be an array');
  process.exit(1);
}

let result = data.slice(0);
let idx = 0;

while (result.length < MIN && idx < data.length) {
  result.push(cloneCase(data[idx % data.length]));
  idx++;
}

console.log(`Gold before=${data.length}, after=${result.length}, target=${MIN}`);
writeJson(filePath, result);
console.log(`✅ Golden set augmented to ${result.length} cases`);


