/**
 * 마이그레이션 실행기
 * 
 * @module data-pg/migrate
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { migrateDir } from './index.js';

// .env 파일 로드 (루트 디렉토리에서)
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
// packages/data-pg/src/migrate.ts -> webcore_appcore_starter_4_17/.env
const rootDir = join(__dirname, '../../..');
const envPath = join(rootDir, '.env');

try {
  const envContent = readFileSync(envPath, 'utf-8');
  for (const line of envContent.split('\n')) {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#')) {
      const [key, ...valueParts] = trimmed.split('=');
      if (key && valueParts.length > 0) {
        const value = valueParts.join('=').trim();
        // 따옴표 제거
        const cleanValue = value.replace(/^["']|["']$/g, '');
        if (!process.env[key]) {
          process.env[key] = cleanValue;
        }
      }
    }
  }
} catch (e) {
  // .env 파일이 없어도 계속 진행 (환경 변수가 이미 설정되어 있을 수 있음)
  console.warn('⚠️  .env file not found, using existing environment variables');
}

migrateDir()
  .then(() => {
    console.log('✅ migrations applied');
    process.exit(0);
  })
  .catch((e) => {
    console.error('❌ migration failed:', e);
    process.exit(1);
  });


