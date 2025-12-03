/**
 * 마이그레이션 실행기
 * 
 * @module data-pg/migrate
 */

import { migrateDir } from './index.js';

migrateDir()
  .then(() => {
    console.log('✅ migrations applied');
    process.exit(0);
  })
  .catch((e) => {
    console.error('❌ migration failed:', e);
    process.exit(1);
  });


