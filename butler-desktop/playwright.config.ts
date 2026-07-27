import { defineConfig, devices } from '@playwright/test';
import {
  createPrivateKey,
  createPublicKey,
  generateKeyPairSync,
  type KeyObject,
} from 'node:crypto';
import { resolve } from 'node:path';

const desktopRoot = resolve(import.meta.dirname);
const repositoryRoot = resolve(desktopRoot, '..');
const appData = resolve(repositoryRoot, '.playwright-runtime', 'app-data');
process.env.BUTLER_E2E_DATA_DIR = appData;
const egressKeyId = 'butler-egress-verifier-playwright-v1';

// Playwright may evaluate this config in both its coordinator and worker
// processes. Reuse the inherited ephemeral key instead of silently generating
// a second key whose private half no longer matches the Vite verifier.
const inheritedPrivateKey =
  process.env.BUTLER_E2E_EGRESS_PRIVATE_KEY_PKCS8_BASE64;
let egressPrivateKey: KeyObject;
if (inheritedPrivateKey) {
  egressPrivateKey = createPrivateKey({
    key: Buffer.from(inheritedPrivateKey, 'base64'),
    format: 'der',
    type: 'pkcs8',
  });
} else {
  egressPrivateKey = generateKeyPairSync('ed25519').privateKey;
}
const egressPublicKey = createPublicKey(egressPrivateKey);
process.env.BUTLER_E2E_EGRESS_PRIVATE_KEY_PKCS8_BASE64 = egressPrivateKey
  .export({ format: 'der', type: 'pkcs8' })
  .toString('base64');
process.env.VITE_EGRESS_RECEIPT_KEY_ID = egressKeyId;
process.env.VITE_EGRESS_RECEIPT_PUBLIC_KEY_SPKI_BASE64 = egressPublicKey
  .export({ format: 'der', type: 'spki' })
  .toString('base64');

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['line'],
    ['junit', { outputFile: 'test-results/playwright-junit.xml' }],
    ['json', { outputFile: 'test-results/playwright-results.json' }],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  use: {
    baseURL: 'http://127.0.0.1:1420',
    trace: 'on',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ...devices['Desktop Chrome'],
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
    deviceScaleFactor: 1,
    reducedMotion: 'reduce',
  },
  webServer: [
    {
      command: 'python3 butler_sidecar.py --host 127.0.0.1 --port 8765',
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
      env: {
        ...process.env,
        VITE_EGRESS_RECEIPT_KEY_ID: egressKeyId,
        VITE_EGRESS_RECEIPT_PUBLIC_KEY_SPKI_BASE64:
          process.env.VITE_EGRESS_RECEIPT_PUBLIC_KEY_SPKI_BASE64,
      },
    },
  ],
});
