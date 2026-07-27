import { defineConfig, devices } from '@playwright/test';
import { resolve } from 'node:path';

const desktopRoot = resolve(import.meta.dirname);
const repositoryRoot = resolve(desktopRoot, '..');
const appData = resolve(repositoryRoot, '.playwright-runtime', 'app-data');
process.env.BUTLER_E2E_DATA_DIR = appData;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['line'],
    ['junit', { outputFile: 'test-results/playwright-junit.xml' }],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:1420',
    trace: 'on',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      command: 'python3 -m butler_pc_core.assets.dev_sidecar --host 127.0.0.1 --port 8765',
      cwd: repositoryRoot,
      url: 'http://127.0.0.1:8765/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        BUTLER_APP_DATA_DIR: appData,
        BUTLER_HOME_BOOTSTRAP_NEW_INSTALL: '1',
        BUTLER_PRODUCTION: '0',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1',
      cwd: desktopRoot,
      url: 'http://127.0.0.1:1420',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
