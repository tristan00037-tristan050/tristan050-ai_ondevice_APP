#!/usr/bin/env node
/**
 * 역할 가드 누락 차단 CI 게이트
 * /admin|/alerts|/exports|/observability 경로의 requireTenantAuth·requireRole() 누락을 차단
 * 
 * @module check_roles_guard
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// 검사할 경로 패턴
const PROTECTED_PATHS = [
  /\/admin\//,
  /\/alerts\//,
  /\/exports\//,
  /\/observability\//,
];

// 필수 미들웨어 패턴
const REQUIRED_MIDDLEWARE = [
  /requireTenantAuth/,
  // 향후 구현: /requireRole\(['"](admin|auditor|operator)['"]\)/
];

/**
 * 파일에서 경로 및 미들웨어 추출
 */
function extractRoutes(filePath, content) {
  const routes = [];
  const lines = content.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    // app.get/post/put/delete 패턴 찾기
    const routeMatch = line.match(/(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]/);
    if (routeMatch) {
      const method = routeMatch[1];
      const path = routeMatch[2];
      
      // 다음 몇 줄에서 미들웨어 확인
      const middleware = [];
      for (let j = i; j < Math.min(i + 10, lines.length); j++) {
        const middlewareLine = lines[j];
        if (middlewareLine.includes('requireTenantAuth')) {
          middleware.push('requireTenantAuth');
        }
        if (middlewareLine.includes('requireRole')) {
          middleware.push('requireRole');
        }
        // 함수 본문 시작 시 중단
        if (middlewareLine.includes('async') || middlewareLine.includes('=>')) {
          break;
        }
      }
      
      routes.push({
        file: filePath,
        line: i + 1,
        method,
        path,
        middleware,
      });
    }
  }

  return routes;
}

/**
 * 파일 검사
 */
function checkFile(filePath) {
  try {
    const content = readFileSync(filePath, 'utf-8');
    const routes = extractRoutes(filePath, content);
    return routes;
  } catch (error) {
    console.error(`Error reading file ${filePath}:`, error.message);
    return [];
  }
}

/**
 * 디렉토리 재귀 검색
 */
function findFiles(dir, extensions = ['.ts', '.js']) {
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
  const collectorSrcPath = join(__dirname, '../packages/collector-node-ts/src');
  const files = findFiles(collectorSrcPath);
  
  const violations = [];
  
  for (const file of files) {
    const routes = checkFile(file);
    
    for (const route of routes) {
      // 보호된 경로인지 확인
      const isProtected = PROTECTED_PATHS.some(pattern => pattern.test(route.path));
      
      if (isProtected) {
        // 필수 미들웨어 확인
        const hasRequiredMiddleware = REQUIRED_MIDDLEWARE.every(pattern =>
          route.middleware.some(mw => pattern.test(mw))
        );
        
        if (!hasRequiredMiddleware) {
          violations.push({
            file: route.file,
            line: route.line,
            method: route.method.toUpperCase(),
            path: route.path,
            missing: REQUIRED_MIDDLEWARE.filter(pattern =>
              !route.middleware.some(mw => pattern.test(mw))
            ).map(p => p.toString()),
          });
        }
      }
    }
  }
  
  // 결과 출력
  if (violations.length > 0) {
    console.error('❌ Role guard violations found:');
    console.error('');
    
    for (const violation of violations) {
      console.error(`  ${violation.file}:${violation.line}`);
      console.error(`    ${violation.method} ${violation.path}`);
      console.error(`    Missing: ${violation.missing.join(', ')}`);
      console.error('');
    }
    
    console.error(`Total violations: ${violations.length}`);
    process.exit(1);
  } else {
    console.log('✅ All protected routes have required middleware');
    process.exit(0);
  }
}

main();


