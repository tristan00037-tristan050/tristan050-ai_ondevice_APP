import { chromium } from "playwright";
import { startModeSwitchServer } from "./mode_switch_server.mjs";

function hardAssert(cond, msg) { if (!cond) throw new Error(msg); }

(async () => {
  const { server, baseURL } = await startModeSwitchServer();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ serviceWorkers: "block" });
    const page = await context.newPage();

    let apiEchoCount = 0;
    let liveHeadersOk = false;

    await page.route("**/api/echo", async (route) => {
      apiEchoCount += 1;
      const headers = route.request().headers();
      const required = ["x-request-id", "x-device-id", "x-role", "x-client-version", "x-mode", "x-ts-utc"];
      liveHeadersOk = required.every((k) => typeof headers[k] === "string" && headers[k].length > 0);
      await route.continue();
    });

    await page.goto(baseURL);

    await page.click("input#mode_mock");
    await page.click("button#run");
    await page.waitForFunction(() => {
      const el = document.querySelector('#result_ok[data-mode="mock"]');
      return el && el.style.display !== 'none';
    }, { timeout: 10000 });
    hardAssert(apiEchoCount === 0, `MOCK must not call /api/echo (count=${apiEchoCount})`);

    await page.click("input#mode_live");
    await page.click("button#run");
    await page.waitForFunction(() => {
      const el = document.querySelector('#result_ok[data-mode="live"]');
      return el && el.style.display !== 'none';
    }, { timeout: 10000 });
    hardAssert(apiEchoCount === 1, `LIVE must call /api/echo exactly once (count=${apiEchoCount})`);
    hardAssert(liveHeadersOk, "LIVE must attach policy header bundle");

    process.exit(0);
  } catch (e) {
    console.error(String(e?.stack ?? e));
    process.exit(1);
  } finally {
    try { await browser?.close(); } catch {}
    try { server?.close(); } catch {}
  }
})();
