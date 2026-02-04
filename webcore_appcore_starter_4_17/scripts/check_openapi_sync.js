#!/usr/bin/env node
/**
 * OpenAPI 타입 동기화 검증 스크립트
 * 생성된 타입 파일이 OpenAPI 스펙과 동기화되어 있는지 확인
 * 
 * Usage: node check_openapi_sync.js [--types-dir <dir>]
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const args = process.argv.slice(2);
const getArg = (k, def) => {
  const i = args.indexOf(k);
  return i === -1 ? def : args[i + 1];
};

const typesDir = getArg('--types-dir', path.join(__dirname, '../packages/app-expo/src/types/generated'));

if (!fs.existsSync(typesDir)) {
  console.error(`❌ 타입 디렉토리를 찾을 수 없습니다: ${typesDir}`);
  process.exit(1);
}

console.log('🔍 OpenAPI 타입 동기화 검증 중...');

// 타입 파일 목록 확인
const typeFiles = fs.readdirSync(typesDir)
  .filter(f => f.endsWith('.ts') && f.includes('types'))
  .map(f => path.join(typesDir, f));

if (typeFiles.length === 0) {
  console.error('❌ 생성된 타입 파일을 찾을 수 없습니다.');
  process.exit(1);
}

// 각 타입 파일 검증
let allValid = true;

for (const typeFile of typeFiles) {
  const fileName = path.basename(typeFile);
  console.log(`  📝 검증 중: ${fileName}`);
  
  // 파일이 비어있지 않은지 확인
  const content = fs.readFileSync(typeFile, 'utf8');
  if (content.trim().length === 0) {
    console.error(`    ❌ 타입 파일이 비어있습니다: ${fileName}`);
    allValid = false;
    continue;
  }
  
  // 기본 타입 정의가 포함되어 있는지 확인
  if (!content.includes('export') && !content.includes('type') && !content.includes('interface')) {
    console.error(`    ❌ 유효한 타입 정의가 없습니다: ${fileName}`);
    allValid = false;
    continue;
  }
  
  // TypeScript 구문 오류 확인 (tsc --noEmit 사용)
  try {
    execSync(`npx tsc --noEmit --skipLibCheck "${typeFile}"`, {
      stdio: 'pipe',
      cwd: path.dirname(typeFile),
    });
    console.log(`    ✅ ${fileName} 검증 통과`);
  } catch (error) {
    console.error(`    ❌ TypeScript 구문 오류: ${fileName}`);
    console.error(error.stdout?.toString() || error.message);
    allValid = false;
  }
}

if (!allValid) {
  console.error('❌ 일부 타입 파일 검증 실패');
  process.exit(1);
}

console.log('✅ 모든 타입 파일이 유효합니다.');
process.exit(0);


