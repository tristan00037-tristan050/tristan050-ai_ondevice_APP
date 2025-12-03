#!/usr/bin/env node
/**
 * 분개 추천 정확도 측정 스크립트
 * 골든셋과 추천 결과를 비교하여 TOP-1/Top-N 정확도 계산
 * 
 * Usage: node measure_accuracy.js [--gold <gold.json>] [--top-n <N>]
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);

// TypeScript 파일을 직접 import하기 위해 tsx 또는 빌드된 파일 사용
// 여기서는 동적 import로 처리
let suggestPostings;
try {
  // 빌드된 파일이 있으면 사용
  const suggestModule = await import('../packages/service-core-accounting/dist/suggest.js');
  suggestPostings = suggestModule.suggestPostings;
} catch {
  // 빌드된 파일이 없으면 tsx로 실행하도록 안내
  console.error('❌ 빌드된 파일을 찾을 수 없습니다. 먼저 빌드하세요:');
  console.error('   cd packages/service-core-accounting && npm run build');
  process.exit(1);
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '..');

const args = process.argv.slice(2);
const getArg = (k, def) => {
  const i = args.indexOf(k);
  return i === -1 ? def : args[i + 1];
};

const goldPath = getArg('--gold', path.join(ROOT_DIR, 'datasets/gold/ledgers.json'));
const topN = parseInt(getArg('--top-n', '5'), 10);

// 골든셋 로드
if (!fs.existsSync(goldPath)) {
  console.error(`❌ 골든셋 파일을 찾을 수 없습니다: ${goldPath}`);
  process.exit(1);
}

const goldData = JSON.parse(fs.readFileSync(goldPath, 'utf8'));
const goldLedgers = Array.isArray(goldData) ? goldData : [goldData];

console.log('📊 분개 추천 정확도 측정');
console.log('='.repeat(60));
console.log(`골든셋: ${goldPath}`);
console.log(`테스트 케이스: ${goldLedgers.length}건`);
console.log(`Top-N: ${topN}`);
console.log('');

let top1Correct = 0;
let topNCorrect = 0;
let totalCases = 0;

// 각 골든셋 항목에 대해 정확도 측정
for (let i = 0; i < goldLedgers.length; i++) {
  const goldLedger = goldLedgers[i];
  
  // 골든셋에서 라인아이템 추출
  let lineItems;
  if (goldLedger.input?.line_items) {
    // 새 포맷 (input.line_items)
    lineItems = goldLedger.input.line_items.map(item => ({
      desc: item.description || item.desc,
      amount: item.amount,
      currency: item.currency || 'KRW',
    }));
  } else if (goldLedger.entries) {
    // 기존 포맷 (entries 기반)
    // entries에서 비용 계정(5xxx, 6xxx)을 찾아서 라인아이템 생성
    const expenseEntries = goldLedger.entries.filter(e => {
      const accountCode = e.account;
      return accountCode && (accountCode.startsWith('5') || accountCode.startsWith('6'));
    });
    
    if (expenseEntries.length > 0) {
      // 비용 계정이 있으면 해당 항목을 라인아이템으로 사용
      lineItems = expenseEntries.map(e => ({
        desc: e.note || 'Unknown',
        amount: parseFloat(e.credit) > 0 ? e.credit : e.debit,
        currency: goldLedger.currency || 'KRW',
      }));
    } else {
      // 비용 계정이 없으면 차변 항목 사용
      lineItems = goldLedger.entries
        .filter(e => parseFloat(e.debit) > 0)
        .map(e => ({
          desc: e.note || 'Unknown',
          amount: e.debit,
          currency: goldLedger.currency || 'KRW',
        }));
    }
  } else {
    console.warn(`⚠️  케이스 #${i + 1}: 라인아이템 없음, 스킵`);
    continue;
  }
  
  if (lineItems.length === 0) {
    console.warn(`⚠️  케이스 #${i + 1}: 라인아이템 없음, 스킵`);
    continue;
  }
  
  // 분개 추천
  const suggestion = suggestPostings({ items: lineItems });
  
  // 골든셋과 비교
  let goldAccounts;
  if (goldLedger.ground_truth?.postings) {
    // 새 포맷 (ground_truth.postings)
    goldAccounts = goldLedger.ground_truth.postings
      .map(p => p.account)
      .filter((v, i, a) => a.indexOf(v) === i); // 중복 제거
  } else if (goldLedger.entries) {
    // 기존 포맷 (entries)
    goldAccounts = goldLedger.entries
      .map(e => e.account)
      .filter((v, i, a) => a.indexOf(v) === i); // 중복 제거
  } else {
    console.warn(`⚠️  케이스 #${i + 1}: 골든셋 계정 없음, 스킵`);
    continue;
  }
  
  // 추천 계정 목록 (postings에서 추출)
  const suggestedAccounts = suggestion.postings
    .map(p => p.account)
    .filter((v, i, a) => a.indexOf(v) === i); // 중복 제거
  
  // alternatives 필드가 있으면 우선 사용 (Top-N 후보)
  const candidateAccounts = suggestion.alternatives && suggestion.alternatives.length > 0
    ? suggestion.alternatives
    : suggestedAccounts;
  
  // 차변/대변 균형 조정 계정(1010, 2010)은 제외
  const nonAdjustmentAccounts = candidateAccounts.filter(acc => acc !== '1010' && acc !== '2010');
  
  // TOP-1 정확도 (첫 번째 추천 계정이 골든셋에 포함되는지)
  if (nonAdjustmentAccounts.length > 0 && goldAccounts.includes(nonAdjustmentAccounts[0])) {
    top1Correct++;
  }
  
  // TOP-N 정확도 (상위 N개 추천 계정 중 하나라도 골든셋에 포함되는지)
  const topNAccounts = nonAdjustmentAccounts.slice(0, topN);
  const hasMatch = topNAccounts.some(acc => goldAccounts.includes(acc));
  if (hasMatch) {
    topNCorrect++;
  }
  
  totalCases++;
  
  console.log(`케이스 #${i + 1}:`);
  console.log(`  골든셋 계정: ${goldAccounts.join(', ')}`);
  console.log(`  추천 계정: ${suggestedAccounts.join(', ')}`);
  console.log(`  신뢰도: ${(suggestion.confidence * 100).toFixed(1)}%`);
  console.log(`  TOP-1: ${suggestedAccounts.length > 0 && goldAccounts.includes(suggestedAccounts[0]) ? '✅' : '❌'}`);
  console.log(`  TOP-${topN}: ${hasMatch ? '✅' : '❌'}`);
  console.log('');
}

// 결과 요약
const top1Accuracy = totalCases > 0 ? (top1Correct / totalCases) * 100 : 0;
const topNAccuracy = totalCases > 0 ? (topNCorrect / totalCases) * 100 : 0;

console.log('='.repeat(60));
console.log('📈 정확도 리포트');
console.log('='.repeat(60));
console.log(`총 테스트 케이스: ${totalCases}건`);
console.log(`TOP-1 정확도: ${top1Correct}/${totalCases} (${top1Accuracy.toFixed(1)}%)`);
console.log(`TOP-${topN} 정확도: ${topNCorrect}/${totalCases} (${topNAccuracy.toFixed(1)}%)`);
console.log('');

// 목표값과 비교
const targetTop1 = 70;
const targetTopN = 85;

if (top1Accuracy >= targetTop1) {
  console.log(`✅ TOP-1 정확도 목표 달성 (${targetTop1}% 이상)`);
} else {
  console.log(`⚠️  TOP-1 정확도 목표 미달 (목표: ${targetTop1}%, 현재: ${top1Accuracy.toFixed(1)}%)`);
}

if (topNAccuracy >= targetTopN) {
  console.log(`✅ TOP-${topN} 정확도 목표 달성 (${targetTopN}% 이상)`);
} else {
  console.log(`⚠️  TOP-${topN} 정확도 목표 미달 (목표: ${targetTopN}%, 현재: ${topNAccuracy.toFixed(1)}%)`);
}

process.exit(0);

