#!/usr/bin/env node
/**
 * Ajv 기반 풀 스키마 검증 (앱 런타임)
 * 경량 검증(validateReportLite)을 Ajv 풀 검증으로 교체
 * 
 * Usage: node validateReportFull.js <qc_report.json> [--schema <schema_path>]
 */

import Ajv from 'ajv';
import addFormats from 'ajv-formats';
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

const reportPath = args[0] || getArg('--report', null);
const schemaPath = getArg('--schema', path.join(__dirname, '../contracts/qc_report.schema.json'));

if (!reportPath) {
  console.error('Usage: node validateReportFull.js <qc_report.json> [--schema <schema_path>]');
  process.exit(2);
}

if (!fs.existsSync(reportPath)) {
  console.error(`Error: Report file not found: ${reportPath}`);
  process.exit(1);
}

if (!fs.existsSync(schemaPath)) {
  console.error(`Error: Schema file not found: ${schemaPath}`);
  process.exit(1);
}

// Ajv 인스턴스 생성 (풀 검증)
const ajv = new Ajv({
  allErrors: true,
  verbose: true,
  strict: true,
  validateFormats: true,
  removeAdditional: false,
});
addFormats(ajv);

// 스키마 로드
const schema = JSON.parse(fs.readFileSync(schemaPath, 'utf8'));
const validate = ajv.compile(schema);

// 리포트 로드 및 검증
const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));

const valid = validate(report);

if (!valid) {
  console.error('❌ 스키마 검증 실패:');
  console.error(JSON.stringify(validate.errors, null, 2));
  process.exit(1);
}

console.log('✅ 스키마 검증 통과');
process.exit(0);

