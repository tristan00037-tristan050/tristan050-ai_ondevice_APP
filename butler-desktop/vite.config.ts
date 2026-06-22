import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { execSync } from 'node:child_process';
import { createRequire } from 'node:module';

const requireJson = createRequire(import.meta.url);
const pkg = requireJson('./package.json') as { version: string };

// 빌드 시점의 git 커밋/브랜치를 헤더 표시에 주입(빌드 추적용). git 이 없으면 안전 폴백.
const commit = (() => {
  try {
    return execSync('git rev-parse --short HEAD').toString().trim();
  } catch {
    return 'dev';
  }
})();
const branch = (() => {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD').toString().trim();
  } catch {
    return 'dev';
  }
})();

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  define: {
    __BUILD_COMMIT__: JSON.stringify(commit),
    __BUILD_BRANCH__: JSON.stringify(branch),
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
  server: { port: 1420, strictPort: true },
  test: {
    globals: false,
    environment: 'jsdom',
    environmentOptions: {
      jsdom: {
        url: 'http://127.0.0.1:8765/',
      },
    },
    setupFiles: ['./src/test-setup.ts'],
  },
});
