#!/usr/bin/env node
/**
 * 레드랙션 커버리지 측정 도구
 * 수집 로그에 대한 마스킹 비율 산정 및 임계 미달 시 경고
 * 
 * Usage: node redactionCoverage.js <log_file> --rules <redact_rules.json> [--threshold <pct>]
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const args = process.argv.slice(2);
const getArg = (k, def) => {
  const i = args.indexOf(k);
  return i === -1 ? def : args[i + 1];
};

const logPath = args[0] || getArg('--log', null);
const rulesPath = getArg('--rules', path.join(__dirname, '../redact/redact_rules.example.json'));
const thresholdPct = parseFloat(getArg('--threshold', '80'));

if (!logPath) {
  console.error('Usage: node redactionCoverage.js <log_file> --rules <redact_rules.json> [--threshold <pct>]');
  process.exit(2);
}

if (!fs.existsSync(logPath)) {
  console.error(`Error: Log file not found: ${logPath}`);
  process.exit(1);
}

if (!fs.existsSync(rulesPath)) {
  console.error(`Error: Rules file not found: ${rulesPath}`);
  process.exit(1);
}

// 레드랙션 규칙 로드
const rulesConfig = JSON.parse(fs.readFileSync(rulesPath, 'utf8'));
const rules = rulesConfig.rules || [];
const guardPct = rulesConfig.over_redaction_guard_pct || 80;

// 로그 파일 읽기
const logContent = fs.readFileSync(logPath, 'utf8');
const originalLength = logContent.length;

if (originalLength === 0) {
  console.warn('⚠️  로그 파일이 비어있습니다.');
  process.exit(0);
}

// 각 규칙 적용 및 커버리지 측정
let redactedContent = logContent;
let totalMatches = 0;
const ruleStats = [];

for (const rule of rules) {
  // (?i) 같은 인라인 플래그를 제거하고 flags로 처리
  let patternStr = rule.pattern;
  let flags = rule.flags || '';
  
  // (?i) 패턴 제거 및 i 플래그 추가
  if (patternStr.includes('(?i)')) {
    patternStr = patternStr.replace(/\(\?i\)/g, '');
    if (!flags.includes('i')) {
      flags += 'i';
    }
  }
  if (patternStr.includes('(?-i)')) {
    patternStr = patternStr.replace(/\(\?-i\)/g, '');
    flags = flags.replace('i', '');
  }
  
  // 기본 플래그 설정 (없으면 'gi')
  if (!flags) {
    flags = 'gi';
  }
  
  try {
    const pattern = new RegExp(patternStr, flags);
    const matches = logContent.match(pattern);
    const matchCount = matches ? matches.length : 0;
    totalMatches += matchCount;
    
    redactedContent = redactedContent.replace(pattern, rule.replacement);
    
    ruleStats.push({
      name: rule.name,
      pattern: patternStr,
      matches: matchCount,
      coverage: matchCount > 0 ? '✅' : '❌',
    });
  } catch (error) {
    console.error(`❌ 규칙 "${rule.name}"의 정규식 오류: ${error.message}`);
    console.error(`   패턴: ${patternStr}`);
    ruleStats.push({
      name: rule.name,
      pattern: patternStr,
      matches: 0,
      coverage: '❌ (정규식 오류)',
    });
  }
}

// 마스킹 비율 계산
const redactedLength = redactedContent.length;
const maskedChars = originalLength - redactedLength;
const maskingRatio = (maskedChars / originalLength) * 100;

// 결과 출력
console.log('📊 레드랙션 커버리지 리포트');
console.log('='.repeat(60));
console.log(`원본 크기: ${originalLength} bytes`);
console.log(`마스킹된 문자 수: ${maskedChars} bytes`);
console.log(`마스킹 비율: ${maskingRatio.toFixed(2)}%`);
console.log(`총 매칭 수: ${totalMatches}`);
console.log('');

console.log('규칙별 상세:');
ruleStats.forEach(stat => {
  console.log(`  ${stat.coverage} ${stat.name}: ${stat.matches}개 매칭`);
});

console.log('');

// 임계값 검증
if (maskingRatio > guardPct) {
  console.error(`❌ 경고: 마스킹 비율(${maskingRatio.toFixed(2)}%)이 과도 마스킹 가드(${guardPct}%)를 초과했습니다.`);
  process.exit(1);
}

if (maskingRatio < thresholdPct && totalMatches > 0) {
  console.warn(`⚠️  경고: 마스킹 비율(${maskingRatio.toFixed(2)}%)이 임계값(${thresholdPct}%) 미만입니다.`);
  console.warn('   레드랙션 규칙이 충분히 적용되지 않았을 수 있습니다.');
  process.exit(1);
}

if (totalMatches === 0) {
  console.warn('⚠️  경고: 레드랙션 규칙이 매칭되지 않았습니다.');
  console.warn('   로그에 민감 정보가 포함되어 있지 않거나 규칙이 부적절할 수 있습니다.');
}

console.log(`✅ 레드랙션 커버리지 검증 통과 (${maskingRatio.toFixed(2)}%)`);
process.exit(0);

