import {
  expect,
  test,
  type Locator,
  type Page,
  type Route,
  type TestInfo,
} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { createHash, createPrivateKey, sign } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const EGRESS_KEY_ID = 'butler-egress-verifier-playwright-v1';

type WireReport = {
  schema_version: string;
  measurement: 'MEASURED';
  value: number;
  run_id: string;
  measurement_generation: number;
  measurement_started_at: string;
  measured_at: string;
  fresh_until?: string;
  egress_bytes_total: number;
  external_request_count: number;
  raw_file_sent_external: boolean;
  verdict: 'PASS' | 'FAIL';
  receipt_run_id: string;
  receipt_key_id: string;
  receipt_algorithm: 'Ed25519';
  receipt_policy_version: string;
  receipt_digest: `sha256:${string}`;
  receipt_signature: string;
};

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

async function installNativeBridge(page: Page): Promise<void> {
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

function canonicalPayload(report: WireReport): Buffer {
  const payload: Record<string, unknown> = {
    schema_version: report.schema_version,
    measurement: report.measurement,
    value: report.value,
    run_id: report.run_id,
    measurement_generation: report.measurement_generation,
    measurement_started_at: report.measurement_started_at,
    measured_at: report.measured_at,
  };
  if (report.fresh_until !== undefined) payload.fresh_until = report.fresh_until;
  Object.assign(payload, {
    egress_bytes_total: report.egress_bytes_total,
    external_request_count: report.external_request_count,
    raw_file_sent_external: report.raw_file_sent_external,
    verdict: report.verdict,
    receipt_run_id: report.receipt_run_id,
    receipt_key_id: report.receipt_key_id,
    receipt_algorithm: report.receipt_algorithm,
    receipt_policy_version: report.receipt_policy_version,
  });
  return Buffer.from(JSON.stringify(payload), 'utf8');
}

function signedReport(
  overrides: Partial<WireReport> = {},
  options: Readonly<{ omitFreshness?: boolean }> = {},
): WireReport {
  const measured = new Date();
  const report: WireReport = {
    schema_version: 'butler.egress.report.v3',
    measurement: 'MEASURED',
    value: overrides.egress_bytes_total ?? 0,
    run_id: 'e2e-run-001',
    measurement_generation: 1,
    measurement_started_at: new Date(measured.getTime() - 1_000).toISOString(),
    measured_at: measured.toISOString(),
    fresh_until: new Date(measured.getTime() + 60_000).toISOString(),
    egress_bytes_total: 0,
    external_request_count: 0,
    raw_file_sent_external: false,
    verdict: 'PASS',
    receipt_run_id: 'e2e-run-001',
    receipt_key_id: EGRESS_KEY_ID,
    receipt_algorithm: 'Ed25519',
    receipt_policy_version: 'egress-policy-2026.1',
    receipt_digest: `sha256:${'0'.repeat(64)}`,
    receipt_signature: 'A'.repeat(86),
    ...overrides,
  };
  if (options.omitFreshness) delete report.fresh_until;
  report.receipt_digest = `sha256:${createHash('sha256')
    .update(canonicalPayload(report))
    .digest('hex')}`;
  const privateKeyBase64 =
    process.env.BUTLER_E2E_EGRESS_PRIVATE_KEY_PKCS8_BASE64;
  if (!privateKeyBase64) throw new Error('E2E_EGRESS_PRIVATE_KEY_MISSING');
  const privateKey = createPrivateKey({
    key: Buffer.from(privateKeyBase64, 'base64'),
    format: 'der',
    type: 'pkcs8',
  });
  report.receipt_signature = sign(
    null,
    Buffer.from(report.receipt_digest, 'utf8'),
    privateKey,
  ).toString('base64url');
  return report;
}

function setupStatus(active: boolean) {
  return {
    schema_version: 'company_profile.status.v1',
    active,
    profile_id: active ? 'company-profile-e2e' : null,
    profile_digest: active ? `sha256:${'b'.repeat(64)}` : null,
    display_hints: {},
    raw_text_logged: false,
    external_send_zero: true,
  };
}

type OpenOptions = Readonly<{
  egress?: (route: Route) => Promise<void> | void;
  learning?: (route: Route) => Promise<void> | void;
  setup?: (route: Route) => Promise<void> | void;
  waitForInput?: boolean;
  useRealLearning?: boolean;
}>;

async function openHome(page: Page, options: OpenOptions = {}): Promise<void> {
  await installNativeBridge(page);
  await page.route(
    '**/v1/company-profile/status',
    options.setup ?? (route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(setupStatus(false)),
    })),
  );
  await page.route(
    '**/api/egress/report',
    options.egress ?? (route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(signedReport()),
    })),
  );
  if (!options.useRealLearning) {
    await page.route(
      '**/api/capabilities/learning',
      options.learning ?? jsonRoute({
        schema_version: 1,
        source: 'UNAVAILABLE',
        generation: 0,
        capabilities: {
          company_rules: 'UNKNOWN',
          company_facts: 'UNKNOWN',
          company_formats: 'UNKNOWN',
          folder_learning: 'UNKNOWN',
        },
      }),
    );
  }
  await page.goto('/');
  await expect(page.getByTestId('sidecar-loading')).toBeHidden({ timeout: 30_000 });
  if (options.waitForInput !== false) {
    await expect(page.getByTestId('text-input')).toBeEnabled();
  }
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}

async function expectNotZero(page: Page): Promise<void> {
  const badge = page.getByTestId('egress-badge');
  await expect(badge).not.toContainText('밖으로 나간 것 0');
}

function jsonRoute(value: unknown, status = 200) {
  return (route: Route) => route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(value),
  });
}

test.describe('egress attack matrix (19/19)', () => {
  test('01 delayed measurement stays loading and never invents zero', async ({ page }) => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>(resolveGate => {
      release = resolveGate;
    });
    await openHome(page, {
      egress: async route => {
        await gate;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(signedReport()),
        });
      },
    });
    await expect(page.getByTestId('egress-badge')).toContainText('확인 중');
    await expectNotZero(page);
    release?.();
    await expect(page.getByTestId('egress-badge')).toContainText('밖으로 나간 것 0');
  });

  test('02 missing measurement is honest and never appears green', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute({
        value: 0,
        measurement: 'STATIC_BETA',
        measured_at: null,
      }),
    });
    const badge = page.getByTestId('egress-badge');
    await expect(badge).toContainText('아직 못 잼');
    await expect(badge).toHaveAttribute('data-tone', 'unmeasured');
    await expect(badge).not.toHaveAttribute('data-tone', 'safe');
    await expectNotZero(page);
  });

  test('03 invalid JSON never appears as zero', async ({ page }) => {
    await openHome(page, {
      egress: route => route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{',
      }),
    });
    await expect(page.getByTestId('egress-badge')).toContainText('확인 실패');
    await expectNotZero(page);
  });

  test('04 missing schema never appears as zero', async ({ page }) => {
    const { schema_version: _schema, ...missing } = signedReport();
    await openHome(page, { egress: jsonRoute(missing) });
    await expect(page.getByTestId('egress-badge')).toContainText('확인 실패');
    await expectNotZero(page);
  });

  test('05 negative byte count is rejected', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({ egress_bytes_total: -1 })),
    });
    await expectNotZero(page);
  });

  test('06 unsafe integer count is rejected', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({
        egress_bytes_total: Number.MAX_SAFE_INTEGER + 1,
      })),
    });
    await expectNotZero(page);
  });

  test('07 missing freshness is verified then shown stale', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({}, { omitFreshness: true })),
    });
    await expect(page.getByTestId('egress-badge')).toContainText('다시 확인 필요');
    await expectNotZero(page);
  });

  test('08 expired freshness is shown stale', async ({ page }) => {
    const measured = new Date(Date.now() - 120_000);
    await openHome(page, {
      egress: jsonRoute(signedReport({
        measurement_started_at: new Date(measured.getTime() - 1_000).toISOString(),
        measured_at: measured.toISOString(),
        fresh_until: new Date(measured.getTime() + 60_000).toISOString(),
      })),
    });
    await expect(page.getByTestId('egress-badge')).toContainText('다시 확인 필요');
    await expectNotZero(page);
  });

  test('09 PASS with positive bytes is rejected', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({ egress_bytes_total: 1 })),
    });
    await expectNotZero(page);
  });

  test('10 PASS with an external request is rejected', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({ external_request_count: 1 })),
    });
    await expectNotZero(page);
  });

  test('11 PASS with raw-file egress is rejected', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({ raw_file_sent_external: true })),
    });
    await expectNotZero(page);
  });

  test('12 FAIL without any observation is rejected', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({ verdict: 'FAIL' })),
    });
    await expectNotZero(page);
  });

  test('13 valid positive FAIL is displayed as a warning', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({
        verdict: 'FAIL',
        egress_bytes_total: 2048,
        external_request_count: 1,
      })),
    });
    const badge = page.getByTestId('egress-badge');
    await expect(badge).toContainText('밖으로 나간 것 2048');
    await expect(badge).toHaveAttribute('data-tone', 'warning');
  });

  test('14 extra schema fields are rejected', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute({ ...signedReport(), extra: 'forbidden' }),
    });
    await expectNotZero(page);
  });

  test('15 newest generation wins an A/B response race', async ({ page }) => {
    let requestCount = 0;
    let releaseA: (() => void) | undefined;
    let settleA: (() => void) | undefined;
    const gateA = new Promise<void>(resolveGate => {
      releaseA = resolveGate;
    });
    const settledA = new Promise<void>(resolveSettled => {
      settleA = resolveSettled;
    });
    await openHome(page, {
      egress: async route => {
        requestCount += 1;
        if (requestCount === 1) {
          await gateA;
          try {
            await route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify(signedReport({
                run_id: 'run-A',
                receipt_run_id: 'run-A',
                measurement_generation: 1,
              })),
            });
          } catch {
            // The product aborts obsolete requests; that is a valid race win.
          } finally {
            settleA?.();
          }
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(signedReport({
            run_id: 'run-B',
            receipt_run_id: 'run-B',
            measurement_generation: 2,
            verdict: 'FAIL',
            egress_bytes_total: 4096,
            external_request_count: 1,
          })),
        });
      },
    });
    await page.getByTestId('egress-badge').click();
    await page.getByRole('button', { name: '다시 확인' }).click();
    const badge = page.getByTestId('egress-badge');
    await expect(badge).toContainText('밖으로 나간 것 4096');
    const winningGeneration = await badge.getAttribute('data-generation');
    expect(Number(winningGeneration)).toBeGreaterThanOrEqual(2);
    releaseA?.();
    await settledA;
    await expect(badge).toContainText('밖으로 나간 것 4096');
    await expect(badge).toHaveAttribute('data-generation', winningGeneration!);
  });

  test('16 signature binds measurement generation', async ({ page }) => {
    const report = signedReport();
    report.measurement_generation += 1;
    await openHome(page, { egress: jsonRoute(report) });
    await expectNotZero(page);
  });

  test('17 signature binds run identity', async ({ page }) => {
    const report = signedReport();
    report.run_id = 'tampered-run';
    report.receipt_run_id = 'tampered-run';
    await openHome(page, { egress: jsonRoute(report) });
    await expectNotZero(page);
  });

  test('18 signature binds measured timestamp', async ({ page }) => {
    const report = signedReport();
    report.measured_at = new Date(Date.now() - 5_000).toISOString();
    await openHome(page, { egress: jsonRoute(report) });
    await expectNotZero(page);
  });

  test('19 receipt run mismatch is rejected even with a valid signature', async ({ page }) => {
    await openHome(page, {
      egress: jsonRoute(signedReport({ receipt_run_id: 'other-run' })),
    });
    await expectNotZero(page);
  });
});

test.describe('FirstScreen v7 required product paths', () => {
  test('실제 sidecar가 불완전 권위를 503으로 닫고 네 행 모두 확인할 수 없습니다로 표시한다', async ({ page }) => {
    test.skip(
      process.env.BUTLER_E2E_PRESEED_LEARNING === '1',
      '사전 권위 데이터가 없는 실제 sidecar 작업에서만 실행합니다.',
    );
    await openHome(page, { useRealLearning: true });
    await page.getByTestId('settings-entry').click();
    const group = page.getByTestId('company-learning-settings');
    await expect(group.getByText('확인할 수 없습니다', { exact: true })).toHaveCount(4);
    await expect(group.getByText('쓰이는 중', { exact: true })).toHaveCount(0);
  });

  test('회사 배우기 네 행이 endpoint 가로채기 없이 실제 sidecar와 권위 저장소에서 계산된다', async ({ page }) => {
    test.skip(
      process.env.BUTLER_E2E_PRESEED_LEARNING !== '1',
      '사전 권위 데이터가 있는 실제 sidecar 작업에서만 실행합니다.',
    );
    await openHome(page, { useRealLearning: true });
    await page.getByTestId('settings-entry').click();
    const group = page.getByTestId('company-learning-settings');
    await expect(group.getByText('쓰이는 중', { exact: true })).toHaveCount(3);
    await expect(group.getByText('미리보기만 됩니다', { exact: true })).toHaveCount(1);
    await expect(group.getByText('확인할 수 없습니다', { exact: true })).toHaveCount(0);
  });

  test('회사 배우기 실제 sidecar 경로가 좁은 창 200퍼센트 확대 키보드 포커스 접근성을 보존한다', async ({ page }) => {
    test.skip(
      process.env.BUTLER_E2E_PRESEED_LEARNING !== '1',
      '사전 권위 데이터가 있는 실제 sidecar 작업에서만 실행합니다.',
    );
    await page.setViewportSize({ width: 640, height: 720 });
    await openHome(page, { useRealLearning: true });
    await page.getByTestId('settings-entry').focus();
    await page.getByTestId('settings-entry').press('Enter');
    await page.evaluate(() => {
      document.documentElement.style.zoom = '2';
    });
    const group = page.getByTestId('company-learning-settings');
    const firstAction = group.getByRole('button', { name: '회사 규칙 등록 열기' });
    await firstAction.focus();
    await expect(firstAction).toBeFocused();
    const axe = await new AxeBuilder({ page })
      .include('[data-testid="company-learning-settings"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(axe.violations, JSON.stringify(axe.violations, null, 2)).toEqual([]);
  });

  test('never-settling egress report leaves loading and never displays a fake zero', async ({ page }) => {
    await openHome(page, {
      egress: async () => new Promise<void>(() => undefined),
    });
    const badge = page.getByTestId('egress-badge');
    await expect(badge).toContainText('확인 중');
    await expect(badge).not.toContainText('밖으로 나간 것 0');
    await expect(badge).toContainText('확인 실패', { timeout: 10_000 });
    await expect(badge).not.toContainText('확인 중');
    await expect(badge).not.toContainText('밖으로 나간 것 0');
    await expect(badge).toHaveAttribute('data-tone', 'error');
  });

  test('company learning shows the four canonical rows with signal-derived statuses', async ({ page }) => {
    await openHome(page, {
      learning: jsonRoute({
        schema_version: 1,
        source: 'CANONICAL',
        generation: 21,
        capabilities: {
          company_rules: 'IN_USE',
          company_facts: 'IN_USE',
          company_formats: 'REGISTERED_ONLY',
          folder_learning: 'PREVIEW_ONLY',
        },
      }),
    });
    await page.getByTestId('settings-entry').click();
    const group = page.getByTestId('company-learning-settings');
    await expect(group).toBeVisible();
    for (const label of [
      '회사 규칙 등록',
      '회사 사실 승인',
      '회사 양식 등록',
      '폴더에서 배우기',
    ]) {
      await expect(group.getByText(label, { exact: true })).toHaveCount(1);
      await expect(group.getByRole('button', { name: `${label} 열기` })).toHaveCount(1);
    }
    await expect(group.getByText('쓰이는 중', { exact: true })).toHaveCount(2);
    await expect(group.getByText('등록만 됩니다', { exact: true })).toHaveCount(1);
    await expect(group.getByText('미리보기만 됩니다', { exact: true })).toHaveCount(1);
  });

  test('company learning preserves four accessible rows when capability signals are unavailable', async ({ page }) => {
    await openHome(page, {
      learning: jsonRoute({ detail: 'CAPABILITY_UNAVAILABLE' }, 503),
    });
    await page.getByTestId('settings-entry').click();
    const group = page.getByTestId('company-learning-settings');
    await expect(group.locator('.settings-row')).toHaveCount(4);
    await expect(group.getByText('확인할 수 없습니다', { exact: true })).toHaveCount(4);
    for (const label of [
      '회사 규칙 등록',
      '회사 사실 승인',
      '회사 양식 등록',
      '폴더에서 배우기',
    ]) {
      await expect(group.getByRole('button', { name: `${label} 열기` })).toHaveCount(1);
    }
  });

  test('preserves compact cards answer area folders and conditional setup banner', async ({ page }) => {
    await page.route('**/api/analyze/stream', route => route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: complete\ndata: {"result_text":"v7 회귀 확인 완료"}\n\n',
    }));
    await openHome(page, { setup: jsonRoute(setupStatus(false)) });
    await expect(page.getByTestId('setup-banner')).toBeVisible();
    await expect(page.getByRole('button', { name: /미분류/ })).toBeVisible();
    await page.getByTestId('text-input').fill('v7 compact regression');
    await page.getByTestId('text-input').press('Enter');
    const messageList = page.getByTestId('message-list');
    await expect(messageList).toBeVisible();
    const grid = page.getByTestId('home-card-grid');
    await expect(grid).toHaveClass(/compact/, { timeout: 30_000 });
    const box = await grid.boundingBox();
    expect(box).not.toBeNull();
    expect(Math.round(box!.height)).toBe(52);
    await expect(messageList).toContainText('v7 회귀 확인 완료');
  });

  test('remains keyboard operable and text-visible at narrow width and 200 percent zoom', async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 720 });
    await openHome(page, {
      learning: jsonRoute({
        schema_version: 1,
        source: 'CANONICAL',
        generation: 31,
        capabilities: {
          company_rules: 'IN_USE',
          company_facts: 'IN_USE',
          company_formats: 'REGISTERED_ONLY',
          folder_learning: 'PREVIEW_ONLY',
        },
      }),
    });
    await page.getByTestId('settings-entry').focus();
    await page.getByTestId('settings-entry').press('Enter');
    await page.evaluate(() => {
      document.documentElement.style.zoom = '2';
    });
    const group = page.getByTestId('company-learning-settings');
    for (const label of [
      '회사 규칙 등록',
      '회사 사실 승인',
      '회사 양식 등록',
      '폴더에서 배우기',
    ]) {
      const text = group.getByText(label, { exact: true });
      await expect(text).toBeVisible();
      expect(await text.evaluate(element => element.scrollWidth <= element.clientWidth + 1))
        .toBe(true);
    }
    const firstAction = group.getByRole('button', { name: '회사 규칙 등록 열기' });
    await firstAction.focus();
    await expect(firstAction).toBeFocused();
    const axe = await new AxeBuilder({ page })
      .include('[data-testid="company-learning-settings"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(axe.violations, JSON.stringify(axe.violations, null, 2)).toEqual([]);
  });
});

type Box = { x: number; y: number; width: number; height: number };

function contains(outer: Box, inner: Box, tolerance = 1): boolean {
  return (
    inner.x >= outer.x - tolerance
    && inner.y >= outer.y - tolerance
    && inner.x + inner.width <= outer.x + outer.width + tolerance
    && inner.y + inner.height <= outer.y + outer.height + tolerance
  );
}

function overlaps(left: Box, right: Box): boolean {
  return !(
    left.x + left.width <= right.x
    || right.x + right.width <= left.x
    || left.y + left.height <= right.y
    || right.y + right.height <= left.y
  );
}

async function expectFullyInside(child: Locator, parent: Locator): Promise<void> {
  const [childBox, parentBox] = await Promise.all([
    child.boundingBox(),
    parent.boundingBox(),
  ]);
  expect(childBox).not.toBeNull();
  expect(parentBox).not.toBeNull();
  expect(contains(parentBox!, childBox!)).toBe(true);
}

for (const viewport of [
  { width: 1440, height: 900, columns: 4 },
  { width: 1280, height: 800, columns: 4 },
  { width: 1024, height: 768, columns: 2 },
  { width: 700, height: 900, columns: 1 },
]) {
  test(`${viewport.width}x${viewport.height} layout geometry`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await openHome(page, {
      setup: jsonRoute(setupStatus(true)),
    });
    const grid = page.getByTestId('home-card-grid');
    const cards = page.getByTestId('home-card');
    await expect(cards).toHaveCount(8);

    if (viewport.width >= 1024) {
      for (let index = 0; index < 8; index += 1) {
        await expectFullyInside(cards.nth(index), grid);
      }
    }
    const positions = await page.locator('[data-home-card="true"]').evaluateAll(elements =>
      elements.map(element => {
        const rect = element.getBoundingClientRect();
        return { x: Math.round(rect.x), y: Math.round(rect.y) };
      }),
    );
    expect(new Set(positions.map(position => position.y)).size).toBe(
      Math.ceil(8 / viewport.columns),
    );

    const inputBox = await page.getByTestId('chat-input').boundingBox();
    expect(inputBox).not.toBeNull();
    expect(contains({ x: 0, y: 0, ...viewport }, inputBox!)).toBe(true);
    const geometry = await page.evaluate(() => ({
      viewport: {
        width: document.documentElement.clientWidth,
        height: document.documentElement.clientHeight,
      },
      scrollWidth: document.documentElement.scrollWidth,
      grid: (() => {
        const rect = document.querySelector('[data-testid="home-card-grid"]')
          ?.getBoundingClientRect();
        return rect
          ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
          : null;
      })(),
    }));
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewport.width + 1);

    if (viewport.width === 1440) {
      const scroll = await grid.evaluate(element => ({
        clientHeight: element.clientHeight,
        scrollHeight: element.scrollHeight,
      }));
      expect(scroll.scrollHeight).toBeLessThanOrEqual(scroll.clientHeight + 1);
      const titles = await page.locator('.home-card-title').all();
      for (const title of titles) {
        const metrics = await title.evaluate(element => {
          const style = getComputedStyle(element);
          return {
            whiteSpace: style.whiteSpace,
            textOverflow: style.textOverflow,
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth,
          };
        });
        expect(metrics.whiteSpace).toBe('nowrap');
        expect(metrics.textOverflow).not.toBe('ellipsis');
        expect(metrics.scrollWidth).toBeLessThanOrEqual(metrics.clientWidth + 1);
      }
    }

    await attachGeometryEvidence(page, testInfo, viewport, geometry);
  });
}

async function attachGeometryEvidence(
  page: Page,
  testInfo: TestInfo,
  viewport: { width: number; height: number },
  geometry: unknown,
): Promise<void> {
  await testInfo.attach(`geometry-${viewport.width}x${viewport.height}.json`, {
    body: Buffer.from(JSON.stringify(geometry, null, 2), 'utf8'),
    contentType: 'application/json',
  });
  await testInfo.attach(`firstscreen-${viewport.width}x${viewport.height}.png`, {
    body: await page.screenshot({ fullPage: true }),
    contentType: 'image/png',
  });
}

test.describe('setup, compact and accessibility matrix', () => {
  test('resolving hides banner until canonical incomplete status arrives', async ({ page }) => {
    let release: (() => void) | undefined;
    const gate = new Promise<void>(resolveGate => {
      release = resolveGate;
    });
    await openHome(page, {
      setup: async route => {
        await gate;
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(setupStatus(false)),
        });
      },
    });
    await expect(page.getByTestId('setup-banner')).toBeHidden();
    release?.();
    await expect(page.getByTestId('setup-banner')).toBeVisible();
  });

  test('canonical incomplete shows banner', async ({ page }) => {
    await openHome(page, { setup: jsonRoute(setupStatus(false)) });
    await expect(page.getByTestId('setup-banner')).toBeVisible();
  });

  test('canonical complete hides banner', async ({ page }) => {
    await openHome(page, { setup: jsonRoute(setupStatus(true)) });
    await expect(page.getByTestId('setup-banner')).toBeHidden();
  });

  test('canonical status unavailable remains fail-closed and actionable', async ({ page }) => {
    await openHome(page, { setup: jsonRoute({ detail: 'unavailable' }, 503) });
    const banner = page.getByTestId('setup-banner');
    await expect(banner).toBeVisible();
    await banner.getByRole('button', { name: '시작하기', exact: true }).click();
    await expect(page.getByTestId('company-profile-setup-modal')).toBeVisible();
  });

  test('dismissal is tab-session scoped and a new page shows the banner', async ({ page, context }) => {
    await openHome(page, { setup: jsonRoute(setupStatus(false)) });
    await page.getByTestId('setup-banner-dismiss').click();
    await expect(page.getByTestId('setup-banner')).toBeHidden();
    await page.reload();
    await expect(page.getByTestId('sidecar-loading')).toBeHidden({ timeout: 30_000 });
    await expect(page.getByTestId('setup-banner')).toBeHidden();

    const newPage = await context.newPage();
    await openHome(newPage, { setup: jsonRoute(setupStatus(false)) });
    await expect(newPage.getByTestId('setup-banner')).toBeVisible();
  });

  test('sessionStorage SecurityError neither crashes nor suppresses banner', async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, 'sessionStorage', {
        configurable: true,
        get() {
          throw new DOMException('blocked', 'SecurityError');
        },
      });
    });
    await openHome(page, { setup: jsonRoute(setupStatus(false)) });
    await expect(page.getByTestId('setup-banner')).toBeVisible();
    await page.getByTestId('setup-banner-dismiss').click();
    await expect(page.getByTestId('setup-banner')).toBeHidden();
    await page.reload();
    await expect(page.getByTestId('setup-banner')).toBeVisible();
  });

  test('setup banner and loading inventory status never overlap', async ({ page }) => {
    let releaseSnapshots: (() => void) | undefined;
    const gate = new Promise<void>(resolveGate => {
      releaseSnapshots = resolveGate;
    });
    await page.route('**/v1/home/snapshot?**', async route => {
      await gate;
      await route.continue().catch(() => undefined);
    });
    await openHome(page, {
      setup: jsonRoute(setupStatus(false)),
      waitForInput: false,
    });
    const inventory = page.locator('.home-inventory-status').first();
    const banner = page.getByTestId('setup-banner');
    await expect(inventory).toBeVisible();
    await expect(banner).toBeVisible();
    const [inventoryBox, bannerBox] = await Promise.all([
      inventory.boundingBox(),
      banner.boundingBox(),
    ]);
    expect(inventoryBox).not.toBeNull();
    expect(bannerBox).not.toBeNull();
    expect(overlaps(inventoryBox!, bannerBox!)).toBe(false);
    releaseSnapshots?.();
  });

  test('message transition preserves the exact 52px compact strip', async ({ page }) => {
    await page.route('**/api/analyze/stream', route => route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: 'event: complete\ndata: {"result_text":"완료"}\n\n',
    }));
    await openHome(page, { setup: jsonRoute(setupStatus(true)) });
    await page.getByTestId('text-input').fill('compact geometry check');
    await page.getByTestId('text-input').press('Enter');
    const grid = page.getByTestId('home-card-grid');
    await expect(grid).toHaveClass(/compact/, { timeout: 30_000 });
    const box = await grid.boundingBox();
    expect(box).not.toBeNull();
    expect(Math.round(box!.height)).toBe(52);
  });

  test('sidebar collapse is keyboard reversible without focus loss', async ({ page }) => {
    await openHome(page, { setup: jsonRoute(setupStatus(true)) });
    const toggle = page.getByTestId('sidebar-toggle-btn');
    await toggle.focus();
    await toggle.press('Enter');
    const closedSidebar = page.locator('.home-sidebar-closed');
    await expect(closedSidebar).toHaveAttribute('aria-hidden', 'true');
    await expect(closedSidebar).toHaveCSS('width', '0px');
    await expect(toggle).toBeFocused();
    await toggle.press('Enter');
    await expect(page.getByTestId('settings-entry')).toBeVisible();
    await expect(toggle).toBeFocused();
  });

  test('single settings entry and shared egress dialog are keyboard-safe', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openHome(page, { setup: jsonRoute(setupStatus(false)) });

    const settings = page.getByRole('button', { name: /^설정$/ });
    await expect(settings).toHaveCount(1);
    await expect(settings).toHaveAttribute('data-testid', 'settings-entry');
    await settings.focus();
    await settings.press('Enter');
    await expect(page.getByRole('dialog', { name: '설정' })).toBeVisible();
    await expect(page.locator('.settings-group')).toHaveCount(7);
    await page.getByRole('button', { name: '설정 닫기' }).click();

    const badge = page.getByTestId('egress-badge');
    await expect(badge).toHaveText('✓밖으로 나간 것 0');
    await badge.click();
    const monitor = page.getByRole('dialog', { name: '외부 전송 상태' });
    await expect(monitor).toHaveAttribute(
      'data-generation',
      await badge.getAttribute('data-generation'),
    );
    await page.keyboard.press('Escape');
    await expect(monitor).toBeHidden();
    await expect(badge).toBeFocused();

    const axe = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(axe.violations, JSON.stringify(axe.violations, null, 2)).toEqual([]);
  });
});
