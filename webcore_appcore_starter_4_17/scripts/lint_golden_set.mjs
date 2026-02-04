/* eslint-disable no-console */
/**
 * 골든셋 린터
 * 개수, PII, 스키마 형식 검증
 * 
 * @module lint_golden_set
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '..');

const args = process.argv.slice(2);
const get = (name, def) => {
  const i = args.findIndex(a => a === `--${name}`);
  return i >= 0 ? args[i + 1] : def;
};

const file = get('file', 'datasets/gold/ledgers.json');
const min = parseInt(get('min', '50'), 10);
const piiMode = (get('pii', 'fail') || 'fail').toLowerCase(); // 'fail' | 'warn'

function isNumStr(s) { return typeof s === 'string' && /^-?\d+(\.\d+)?$/.test(s); }
function hasDesc(li) { return typeof li?.description === 'string' || typeof li?.desc === 'string'; }
function pickDesc(li) { return li?.description ?? li?.desc ?? ''; }

function detectPII(text) {
  if (typeof text !== 'string' || !text) return false;
  const patterns = [
    /\b\d{13,16}\b/,                 // 연속 숫자 13~16 (카드/계좌 유사)
    /\b\d{3}-\d{2}-\d{5}\b/,         // 사업자등록번호 패턴 유사
    /\b\d{6}-\d{7}\b/,               // 주민등록번호 유사
    /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i // 이메일
  ];
  return patterns.some(re => re.test(text));
}

function assert(cond, msg) { if (!cond) throw new Error(msg); }

try {
  const p = path.isAbsolute(file) ? file : path.join(ROOT_DIR, file);
  const raw = fs.readFileSync(p, 'utf8');
  const data = JSON.parse(raw);

  assert(Array.isArray(data), '골든셋 JSON이 배열이어야 합니다.');
  console.log(`golden set size = ${data.length}`);
  assert(data.length >= min, `골든셋 최소 개수 미달: ${data.length} < ${min}`);

  let piiHits = 0;
  let invalid = 0;

  data.forEach((sample, idx) => {
    const loc = `#${idx + 1} id=${sample?.id ?? '(no-id)'}`;

    // 기본 필드 (새 포맷 우선, 기존 포맷도 허용)
    if (sample.input?.line_items) {
      // 새 포맷
      assert(typeof sample?.policy_version === 'string' || !sample.policy_version, `${loc}: policy_version 유형 오류`);
      assert(Array.isArray(sample.input.line_items) && sample.input.line_items.length > 0, `${loc}: input.line_items 누락/비어있음`);
      assert(sample?.ground_truth && Array.isArray(sample.ground_truth.postings) && sample.ground_truth.postings.length > 0, `${loc}: ground_truth.postings 누락/비어있음`);

      // 라인아이템 검증
      for (const li of sample.input.line_items) {
        assert(hasDesc(li), `${loc}: line_item에 desc/description 누락`);
        assert(isNumStr(li.amount), `${loc}: line_item.amount는 문자열 숫자여야 함`);
        if (detectPII(pickDesc(li))) piiHits++;
      }

      // 정답 분개 검증
      for (const po of sample.ground_truth.postings) {
        assert(typeof po.account === 'string' && po.account, `${loc}: posting.account 누락`);
        assert(isNumStr(po.debit ?? '0'), `${loc}: posting.debit는 문자열 숫자여야 함`);
        assert(isNumStr(po.credit ?? '0'), `${loc}: posting.credit는 문자열 숫자여야 함`);
        if (detectPII(po.account)) piiHits++;
      }
    } else if (sample.entries) {
      // 기존 포맷 (entries 기반) - 호환성 유지
      assert(Array.isArray(sample.entries) && sample.entries.length > 0, `${loc}: entries 누락/비어있음`);
      assert(typeof sample.currency === 'string', `${loc}: currency 누락`);
      
      for (const entry of sample.entries) {
        assert(typeof entry.account === 'string' && entry.account, `${loc}: entry.account 누락`);
        assert(isNumStr(entry.debit ?? '0'), `${loc}: entry.debit는 문자열 숫자여야 함`);
        assert(isNumStr(entry.credit ?? '0'), `${loc}: entry.credit는 문자열 숫자여야 함`);
        if (entry.note && detectPII(entry.note)) piiHits++;
      }
    } else {
      throw new Error(`${loc}: input.line_items 또는 entries 필수`);
    }
  });

  if (piiHits > 0) {
    const msg = `골든셋 내 PII 의심 패턴 ${piiHits}건 탐지`;
    if (piiMode === 'fail') {
      throw new Error(msg);
    } else {
      console.warn(`WARN: ${msg}`);
    }
  }

  console.log('✅ 골든셋 검증 통과');
} catch (e) {
  console.error(`❌ 골든셋 검증 실패: ${e.message || e}`);
  process.exit(1);
}


