#!/usr/bin/env node
/**
 * 회계 스키마 검증 스크립트 (Ajv 기반)
 * ledger_posting.schema.json, export_manifest.schema.json 검증
 * 
 * Usage: node validate_accounting.js [--posting <posting.json>] [--manifest <manifest.json>]
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
const postingPath = getArg('--posting', path.join(ROOT_DIR, 'datasets/gold/ledgers.json'));
const manifestPath = getArg('--manifest', null);
const postingSchemaPath = path.join(ROOT_DIR, 'contracts/ledger_posting.schema.json');
const manifestSchemaPath = path.join(ROOT_DIR, 'contracts/export_manifest.schema.json');

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

// 분개 스키마 검증
if (fs.existsSync(postingPath) && fs.existsSync(postingSchemaPath)) {
  console.log('📋 분개 스키마 검증 중...');
  const postingSchema = JSON.parse(fs.readFileSync(postingSchemaPath, 'utf8'));
  const validatePosting = ajv.compile(postingSchema);
  
  const postingData = JSON.parse(fs.readFileSync(postingPath, 'utf8'));
  // 배열인 경우 각 항목 검증
  const postings = Array.isArray(postingData) ? postingData : [postingData];
  
  for (let i = 0; i < postings.length; i++) {
    const posting = postings[i];
    const valid = validatePosting(posting);
    
    if (!valid) {
      console.error(`❌ 분개 #${i + 1} 검증 실패:`);
      console.error(JSON.stringify(validatePosting.errors, null, 2));
      allValid = false;
    } else {
      console.log(`✅ 분개 #${i + 1} 검증 통과`);
    }
  }
} else {
  console.warn(`⚠️  분개 파일 또는 스키마를 찾을 수 없습니다: ${postingPath}, ${postingSchemaPath}`);
}

// Export 매니페스트 스키마 검증
if (manifestPath && fs.existsSync(manifestPath) && fs.existsSync(manifestSchemaPath)) {
  console.log('📋 Export 매니페스트 스키마 검증 중...');
  const manifestSchema = JSON.parse(fs.readFileSync(manifestSchemaPath, 'utf8'));
  const validateManifest = ajv.compile(manifestSchema);
  
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const valid = validateManifest(manifest);
  
  if (!valid) {
    console.error('❌ Export 매니페스트 검증 실패:');
    console.error(JSON.stringify(validateManifest.errors, null, 2));
    allValid = false;
  } else {
    console.log('✅ Export 매니페스트 검증 통과');
  }
} else if (manifestPath) {
  console.warn(`⚠️  Export 매니페스트 파일을 찾을 수 없습니다: ${manifestPath}`);
}

// 결과
if (allValid) {
  console.log('\n✅ 모든 회계 스키마 검증 통과');
  process.exit(0);
} else {
  console.error('\n❌ 일부 스키마 검증 실패');
  process.exit(1);
}


