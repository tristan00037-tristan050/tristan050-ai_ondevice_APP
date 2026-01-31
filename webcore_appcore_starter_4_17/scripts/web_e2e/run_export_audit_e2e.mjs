import { chromium } from "playwright";
import { startExportAuditServer } from "./export_audit_server.mjs";

function hardAssert(cond, msg) { if (!cond) throw new Error(msg); }

(async () => {
  const { server, baseURL } = await startExportAuditServer();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ serviceWorkers: "block" });
    const page = await context.newPage();

    let previewCount = 0;
    let approveCount = 0;
    let approveAuditIds = [];
    let approveIdemKeys = [];

    // preview/approve 요청 카운트 + payload/헤더 검증(클라 레벨)
    await page.route("**/api/preview", async (route) => {
      previewCount += 1;
      const headers = route.request().headers();
      const required = ["x-request-id", "x-device-id", "x-role", "x-client-version", "x-mode", "x-ts-utc", "x-policy-version"];
      hardAssert(required.every((k) => typeof headers[k] === "string" && headers[k].length > 0), "PREVIEW headers missing");

      const json = route.request().postDataJSON?.() ?? {};
      const keys = Object.keys(json);
      hardAssert(keys.every((k) => ["request_id", "mode", "signals"].includes(k)), "PREVIEW meta-only violation");
      await route.continue();
    });

    await page.route("**/api/approve", async (route) => {
      approveCount += 1;
      const headers = route.request().headers();
      hardAssert(typeof headers["x-idempotency-key"] === "string" && headers["x-idempotency-key"].length > 0, "APPROVE missing idempotency key");
      approveIdemKeys.push(headers["x-idempotency-key"]);

      const json = route.request().postDataJSON?.() ?? {};
      const keys = Object.keys(json);
      const allow = ["request_id", "mode", "export_token_hash", "policy_version", "signals"];
      hardAssert(keys.every((k) => allow.includes(k)), "APPROVE meta-only violation");
      await route.continue();
    });

    await page.goto(baseURL);

    // 1) preview 1회
    await page.click("button#preview");
    await page.waitForFunction(() => {
      const el = document.querySelector('#result_ok[data-step="preview"]');
      return el && el.style.display !== "none";
    }, { timeout: 10000 });
    hardAssert(previewCount === 1, `PREVIEW must be called exactly once (count=${previewCount})`);

    // 2) approve 2회 (멱등 검증)
    await page.click("button#approve");
    await page.waitForFunction(() => {
      const el = document.querySelector('#result_ok[data-step="approve"]');
      return el && el.style.display !== "none";
    }, { timeout: 10000 });

    // 첫 approve 결과에서 audit id 읽기
    let firstAuditId = await page.evaluate(() => {
      const t = document.querySelector("#out")?.textContent ?? "";
      try { return JSON.parse(t).audit_event_v2_id ?? ""; } catch { return ""; }
    });
    hardAssert(typeof firstAuditId === "string" && firstAuditId.length > 0, "APPROVE must return audit_event_v2_id");

    // 두 번째 approve
    await page.click("button#approve");
    await page.waitForFunction(() => {
      const el = document.querySelector('#result_ok[data-step="approve"]');
      return el && el.style.display !== "none";
    }, { timeout: 10000 });

    let secondAuditId = await page.evaluate(() => {
      const t = document.querySelector("#out")?.textContent ?? "";
      try { return JSON.parse(t).audit_event_v2_id ?? ""; } catch { return ""; }
    });
    hardAssert(secondAuditId === firstAuditId, "IDEMPOTENT: second approve must return same audit id");

    hardAssert(approveCount === 2, `APPROVE must be called twice (count=${approveCount})`);
    hardAssert(approveIdemKeys.length === 2 && approveIdemKeys[0] === approveIdemKeys[1], "IDEMPOTENT: idempotency key must be stable");

    // 3) 서버 내부 audit_count_total이 1인지 확인
    const stats = await page.evaluate(async () => {
      const r = await fetch("/api/audit_stats");
      return r.json();
    });
    hardAssert(stats.audit_count_total === 1, `AUDIT must be written exactly once (count=${stats.audit_count_total})`);

    process.exit(0);
  } catch (e) {
    console.error(String(e?.stack ?? e));
    process.exit(1);
  } finally {
    try { await browser?.close(); } catch {}
    try { server?.close(); } catch {}
  }
})();

