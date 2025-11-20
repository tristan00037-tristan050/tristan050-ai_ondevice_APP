#!/usr/bin/env node
/**
 * 전체 스키마 검증 스크립트 (Ajv 기반)
 * 정책/리포트 샘플 검증
 * 
 * Usage: node validate_all.js [--policy <policy.json>] [--report <report.json>]
 */

import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.join(__dirname, '..');

const args = process.argv.slice(2);
const getArg = (k, def) => {
  const i = args.indexOf(k);
  return i === -1 ? def : args[i + 1];
};

// 기본 경로
const policyPath = getArg('--policy', path.join(ROOT_DIR, 'configs/webcore_qc_policy.example.json'));
const reportPath = getArg('--report', path.join(ROOT_DIR, 'examples/qc_snapshot.example.json'));
const policySchemaPath = path.join(ROOT_DIR, 'contracts/qc_policy.schema.json');
const reportSchemaPath = path.join(ROOT_DIR, 'contracts/qc_report.schema.json');

// Ajv 인스턴스 생성
const ajv = new Ajv({
  allErrors: true,
  verbose: true,
  strict: true,
  validateFormats: true,
  removeAdditional: false,
});
addFormats(ajv);

let allValid = true;

// 정책 스키마 검증
if (fs.existsSync(policyPath) && fs.existsSync(policySchemaPath)) {
  console.log('📋 정책 스키마 검증 중...');
  const policySchema = JSON.parse(fs.readFileSync(policySchemaPath, 'utf8'));
  const validatePolicy = ajv.compile(policySchema);
  
  const policy = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
  const valid = validatePolicy(policy);
  
  if (!valid) {
    console.error('❌ 정책 스키마 검증 실패:');
    console.error(JSON.stringify(validatePolicy.errors, null, 2));
    allValid = false;
  } else {
    console.log('✅ 정책 스키마 검증 통과');
  }
} else {
  console.warn(`⚠️  정책 파일 또는 스키마를 찾을 수 없습니다: ${policyPath}`);
}

// 리포트 스키마 검증
if (fs.existsSync(reportPath) && fs.existsSync(reportSchemaPath)) {
  console.log('📊 리포트 스키마 검증 중...');
  const reportSchema = JSON.parse(fs.readFileSync(reportSchemaPath, 'utf8'));
  const validateReport = ajv.compile(reportSchema);
  
  const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  const valid = validateReport(report);
  
  if (!valid) {
    console.error('❌ 리포트 스키마 검증 실패:');
    console.error(JSON.stringify(validateReport.errors, null, 2));
    allValid = false;
  } else {
    console.log('✅ 리포트 스키마 검증 통과');
  }
} else {
  console.warn(`⚠️  리포트 파일 또는 스키마를 찾을 수 없습니다: ${reportPath}`);
}

if (!allValid) {
  console.error('❌ 일부 검증 실패');
  process.exit(1);
}

console.log('✅ 모든 스키마 검증 통과');
process.exit(0);

