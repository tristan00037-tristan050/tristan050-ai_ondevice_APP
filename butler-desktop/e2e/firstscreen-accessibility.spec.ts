import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

async function capabilityToken(): Promise<string> {
  const dataDir = process.env.BUTLER_E2E_DATA_DIR;
  if (!dataDir) throw new Error('BUTLER_E2E_DATA_DIR_MISSING');
  const tokenPath = resolve(dataDir, 'ipc', 'sidecar.capability');
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const token = (await readFile(tokenPath, 'utf8')).trim();
      if (token) return token;
    } catch {
      await new Promise(resolveWait => setTimeout(resolveWait, 100));
    }
  }
  throw new Error('E2E_CAPABILITY_TOKEN_UNAVAILABLE');
}

async function installNativeBridge(page: import('@playwright/test').Page): Promise<void> {
  const token = await capabilityToken();
  await page.addInitScript(({ capability }) => {
    const target = window as typeof window & {
      __TAURI_INTERNALS__?: { invoke?: (command: string) => Promise<unknown> };
    };
    target.__TAURI_INTERNALS__ = {
      ...(target.__TAURI_INTERNALS__ ?? {}),
      invoke: async (command: string) => {
        if (command === 'get_sidecar_capability_token') return capability;
        if (command === 'plugin:app|version') return '0.9.0';
        throw new Error('E2E_UNSUPPORTED_NATIVE_COMMAND');
      },
    };
  }, { capability: token });
}

async function assertWcag22AA(page: import('@playwright/test').Page): Promise<void> {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(result.violations, JSON.stringify(result.violations, null, 2)).toEqual([]);
}

test.beforeEach(async ({ page }) => {
  await installNativeBridge(page);
  await page.goto('/');
  await expect(page.getByTestId('sidecar-loading')).toBeHidden({ timeout: 30_000 });
  await expect(page.getByTestId('text-input')).toBeEnabled();
});

test('actual first screen, folder, search, conversation, modal and trash flows meet WCAG 2.2 AA', async ({ page }) => {
  await assertWcag22AA(page);

  await page.keyboard.press('Tab');
  await expect(page.getByTestId('new-conv-btn')).toBeFocused();
  const outlineStyle = await page.getByTestId('new-conv-btn').evaluate(element => getComputedStyle(element).outlineStyle);
  expect(outlineStyle).not.toBe('none');

  const unique = `E2E-${Date.now()}`;
  const folderName = `접근성-${unique}`;
  await page.getByLabel('새 폴더 이름').fill(folderName);
  await page.getByLabel('새 폴더 이름').press('Enter');
  await expect(page.getByText(folderName, { exact: true })).toBeVisible();

  const request = `접근성 실제 대화 ${unique}`;
  await page.getByLabel('Butler에게 보낼 요청').fill(request);
  await page.getByLabel('Butler에게 보낼 요청').press('Enter');
  await expect(page.getByText(request, { exact: true })).toBeVisible({ timeout: 20_000 });
  const stop = page.getByTestId('cancel-btn');
  if (await stop.isVisible()) {
    await stop.focus();
    await stop.press('Enter');
  }

  await page.getByLabel('대화 제목 검색').fill(unique);
  await expect(page.getByText(request, { exact: true })).toBeVisible();
  await assertWcag22AA(page);

  const menu = page.getByTestId('conv-menu-btn').first();
  await menu.focus();
  await menu.press('Enter');
  await page.getByTestId('delete-menu-item').press('Enter');
  const dialog = page.getByRole('dialog', { name: '대화 삭제' });
  await expect(dialog).toBeVisible();
  await expect(page.getByTestId('delete-cancel-btn')).toBeFocused();
  await assertWcag22AA(page);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(menu).toBeFocused();

  await menu.press('Enter');
  await page.getByTestId('delete-menu-item').press('Enter');
  await page.getByTestId('delete-confirm-btn').press('Enter');
  await expect(page.getByText(request, { exact: true })).toBeHidden();
  await page.getByRole('button', { name: /휴지통/ }).press('Enter');
  await expect(page.getByRole('button', { name: '복원' }).first()).toBeVisible();
  await assertWcag22AA(page);
});

test('network fault exposes an accessible raw-safe error alert', async ({ page }) => {
  await page.route('**/v1/home/**', route => route.abort('failed'));
  await page.getByLabel('대화 제목 검색').fill(`fault-${Date.now()}`);
  const alert = page.getByRole('alert').first();
  await expect(alert).toBeVisible();
  await expect(alert).not.toContainText(/Authorization|Bearer|sidecar\.capability|\/Users\//i);
  await assertWcag22AA(page);
});
