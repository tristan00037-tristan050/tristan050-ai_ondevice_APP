import { chromium } from "playwright";
import { startMetaOnlyNegativeServer } from "./meta_only_negative_server.mjs";

function hardAssert(cond, msg) { if (!cond) throw new Error(msg); }

(async () => {
  const { server, baseURL } = await startMetaOnlyNegativeServer();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ serviceWorkers: "block" });
    const page = await context.newPage();

    let apiCount = 0;
    await page.route("**/api/meta", async (route) => {
      apiCount += 1;
      await route.continue();
    });

    await page.goto(baseURL);
    await page.click("button#run");

    await page.waitForFunction(() => {
      const el = document.querySelector("#result_ok");
      return el && el.style.display !== "none";
    }, { timeout: 15000 });

    // 최소 6케이스 → 6회 이상 호출되어야 정상
    hardAssert(apiCount >= 6, `expected >=6 /api/meta calls, got ${apiCount}`);

    // out이 JSON인지 확인(실패면 페이지가 throw로 종료)
    const outText = await page.evaluate(() => document.querySelector("#out")?.textContent ?? "");
    JSON.parse(outText);

    process.exit(0);
  } catch (e) {
    console.error(String(e?.stack ?? e));
    process.exit(1);
  } finally {
    try { await browser?.close(); } catch {}
    try { server?.close(); } catch {}
  }
})();

