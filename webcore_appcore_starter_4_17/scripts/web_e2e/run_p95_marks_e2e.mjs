import { chromium } from "playwright";
import { startP95MarksServer } from "./p95_marks_server.mjs";

function hardAssert(cond, msg) { if (!cond) throw new Error(msg); }

(async () => {
  const { server, baseURL } = await startP95MarksServer();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ serviceWorkers: "block" });
    const page = await context.newPage();

    let reqHeaderSeen = "";
    let runtimeHeadersOk = false;
    let callCount = 0;

    await page.route("**/api/three_blocks", async (route) => {
      callCount += 1;
      const headers = route.request().headers();
      reqHeaderSeen = headers["x-request-id"] ?? "";
      runtimeHeadersOk = true; // server always returns headers; we validate after response render
      await route.continue();
    });

    await page.goto(baseURL);

    await page.click("button#run");
    await page.waitForFunction(() => {
      const el = document.querySelector("#result_ok");
      return el && el.style.display !== "none";
    }, { timeout: 10000 });

    hardAssert(callCount === 1, `three_blocks must be called exactly once (count=${callCount})`);

    const data = await page.evaluate(() => {
      const el = document.querySelector("#result_ok");
      return {
        requestId: el?.dataset?.requestId ?? "",
        inputDoneTs: Number(el?.dataset?.inputDoneTs ?? "NaN"),
        renderDoneTs: Number(el?.dataset?.renderDoneTs ?? "NaN"),
        outText: document.querySelector("#out")?.textContent ?? "",
      };
    });

    hardAssert(typeof data.requestId === "string" && data.requestId.length >= 6, "request_id missing on UI marker");
    hardAssert(reqHeaderSeen === data.requestId, "PARITY: x-request-id must equal UI request_id");
    hardAssert(Number.isFinite(data.inputDoneTs), "input_done_ts missing");
    hardAssert(Number.isFinite(data.renderDoneTs), "render_done_ts missing");
    hardAssert(data.renderDoneTs >= data.inputDoneTs, "MARKS_ORDER_BAD");

    // Also ensure runtime headers were captured into JSON output
    const parsed = JSON.parse(data.outText);
    hardAssert(typeof parsed.runtime?.manifest_sha256 === "string" && parsed.runtime.manifest_sha256.length > 10, "runtime manifest sha missing in UI output");

    process.exit(0);
  } catch (e) {
    console.error(String(e?.stack ?? e));
    process.exit(1);
  } finally {
    try { await browser?.close(); } catch {}
    try { server?.close(); } catch {}
  }
})();

