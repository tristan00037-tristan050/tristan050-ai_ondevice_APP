#!/usr/bin/env node
/**
 * 클라이언트 측 필터/집계 금지 CI 게이트
 * 서버사이드 필터/페이지네이션만 허용, 클라이언트 필터/집계 금지
 * 
 * @module check_client_filter
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 금지된 패턴 (클라이언트 측 필터/집계)
const FORBIDDEN_PATTERNS = [
  // useMemo로 필터링
  /useMemo\s*\([^)]*filter[^)]*\)/i,
  // Array.filter()로 필터링 (서버 응답 후)
  /\.filter\s*\([^)]*severity[^)]*\)/i,
  /\.filter\s*\([^)]*policyVersion[^)]*\)/i,
  /\.filter\s*\([^)]*since[^)]*\)/i,
  // Array.reduce()로 집계
  /\.reduce\s*\([^)]*severity[^)]*\)/i,
  // 클라이언트 측 페이지네이션
  /\.slice\s*\([^)]*page[^)]*\)/i,
  /\.slice\s*\([^)]*limit[^)]*\)/i,
];

// 허용된 패턴 (서버 응답 처리)
const ALLOWED_PATTERNS = [
  // 서버 응답에서 데이터 추출
  /response\.reports/,
  /response\.pagination/,
  // ID 필터 (클라이언트 측 검색은 허용)
  /\.filter\s*\([^)]*id[^)]*toLowerCase/,
];

/**
 * 파일 검사
 */
function checkFile(filePath) {
  try {
    const content = readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');
    const violations = [];
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      
      // 금지된 패턴 확인
      for (const pattern of FORBIDDEN_PATTERNS) {
        if (pattern.test(line)) {
          // 허용된 패턴인지 확인
          const isAllowed = ALLOWED_PATTERNS.some(allowed => allowed.test(line));
          
          if (!isAllowed) {
            violations.push({
              file: filePath,
              line: i + 1,
              pattern: pattern.toString(),
              code: line.trim(),
            });
          }
        }
      }
    }
    
    return violations;
  } catch (error) {
    console.error(`Error reading file ${filePath}:`, error.message);
    return [];
  }
}

/**
 * 디렉토리 재귀 검색
 */
function findFiles(dir, extensions = ['.ts', '.tsx', '.js', '.jsx']) {
  const files = [];
  
  try {
    const entries = readdirSync(dir);
    
    for (const entry of entries) {
      const fullPath = join(dir, entry);
      const stat = statSync(fullPath);
      
      if (stat.isDirectory() && !entry.startsWith('.') && entry !== 'node_modules') {
        files.push(...findFiles(fullPath, extensions));
      } else if (stat.isFile() && extensions.some(ext => entry.endsWith(ext))) {
        files.push(fullPath);
      }
    }
  } catch (error) {
    console.error(`Error reading directory ${dir}:`, error.message);
  }
  
  return files;
}

/**
 * 메인 검사 함수
 */
function main() {
  // Ops Console 소스만 검사 (클라이언트 측)
  const opsConsoleSrcPath = join(__dirname, '../packages/ops-console/src');
  const files = findFiles(opsConsoleSrcPath);
  
  const violations = [];
  
  for (const file of files) {
    const fileViolations = checkFile(file);
    violations.push(...fileViolations);
  }
  
  // 결과 출력
  if (violations.length > 0) {
    console.error('❌ Client-side filtering/aggregation violations found:');
    console.error('');
    
    for (const violation of violations) {
      console.error(`  ${violation.file}:${violation.line}`);
      console.error(`    Pattern: ${violation.pattern}`);
      console.error(`    Code: ${violation.code}`);
      console.error('');
    }
    
    console.error(`Total violations: ${violations.length}`);
    console.error('');
    console.error('💡 Fix: Use server-side filtering via API query parameters instead');
    process.exit(1);
  } else {
    console.log('✅ No client-side filtering/aggregation violations found');
    process.exit(0);
  }
}

main();

