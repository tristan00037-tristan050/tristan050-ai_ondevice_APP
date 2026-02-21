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

// buildSha: GIT_SHA env (Docker/CI) or git rev-parse HEAD (로컬). 주입 없으면 git 필수(fail-closed)
const injectedSha = process.env.GIT_SHA && process.env.GIT_SHA.trim();
const isValid40Hex = (s) => typeof s === 'string' && s.length === 40 && /^[0-9a-f]{40}$/i.test(s);

let buildSha = '';
if (isValid40Hex(injectedSha)) {
  buildSha = injectedSha;
} else {
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
}

// ✅ P0: build_info 생성 실패는 빌드 FAIL로 강제
if (!buildSha || buildSha.length !== 40) {
  console.error('[build_info] Invalid buildSha:', buildSha);
  process.exit(1);
}

// 정규식 40-hex 검증
if (!/^[0-9a-f]{40}$/i.test(buildSha)) {
  console.error('[build_info] buildSha is not 40-hex:', buildSha);
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

