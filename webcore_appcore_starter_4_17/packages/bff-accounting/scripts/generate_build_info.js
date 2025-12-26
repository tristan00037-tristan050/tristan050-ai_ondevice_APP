#!/usr/bin/env node
/**
 * ✅ S6-S7: Build-time build info generator
 * 빌드 시 dist/build_info.json을 생성하여 buildSha/buildTime을 고정 기록
 * 런타임 git 계산 금지 (게이트 무력화 방지)
 */

import { writeFileSync, mkdirSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// scripts/generate_build_info.js → packages/bff-accounting/dist/build_info.json
const PKG_ROOT = resolve(__dirname, '..');
const DIST_DIR = resolve(PKG_ROOT, 'dist');
const BUILD_INFO_PATH = resolve(DIST_DIR, 'build_info.json');

// buildSha: git rev-parse HEAD (풀 40자)
// git repo root 찾기 (packages/bff-accounting에서 상위로 올라가서 .git 찾기)
let gitRoot = PKG_ROOT;
for (let i = 0; i < 10; i++) {
  if (existsSync(resolve(gitRoot, '.git'))) {
    break;
  }
  const parent = dirname(gitRoot);
  if (parent === gitRoot) {
    gitRoot = '';
    break;
  }
  gitRoot = parent;
}

if (!gitRoot) {
  console.error('[build_info] Failed to find git root');
  process.exit(1);
}

let buildSha = '';
try {
  buildSha = execSync('git rev-parse HEAD', {
    encoding: 'utf-8',
    cwd: gitRoot,
    stdio: 'pipe',
  }).trim();
} catch (error) {
  console.error('[build_info] Failed to get git HEAD:', error.message);
  process.exit(1);
}

if (!buildSha || buildSha.length !== 40) {
  console.error('[build_info] Invalid buildSha:', buildSha);
  process.exit(1);
}

// buildShaShort: 7자
const buildShaShort = buildSha.substring(0, 7);

// buildTime: ISO8601 (현재 시각)
const buildTime = new Date().toISOString();

// build_info.json 생성
const buildInfo = {
  buildSha: buildSha,
  buildShaShort: buildShaShort,
  buildTime: buildTime,
};

// dist 디렉토리 생성 (없으면)
mkdirSync(DIST_DIR, { recursive: true });

// 파일 쓰기
writeFileSync(
  BUILD_INFO_PATH,
  JSON.stringify(buildInfo, null, 2) + '\n',
  'utf-8'
);

console.log('[build_info] Generated:', BUILD_INFO_PATH);
console.log('[build_info] buildSha:', buildSha);
console.log('[build_info] buildTime:', buildTime);

