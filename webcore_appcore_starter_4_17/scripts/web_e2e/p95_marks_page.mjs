const out = document.querySelector("#out");
const resultOk = document.querySelector("#result_ok");
const runBtn = document.querySelector("#run");

function nowIsoUtc() { return new Date().toISOString(); }

function perfNowMs() {
  // browser high-res time
  return Math.round(performance.now());
}

function rid() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return [...a].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function buildHeaders({ requestId }) {
  return {
    "content-type": "application/json",
    "x-request-id": requestId,
    "x-device-id": "device_hash_demo",
    "x-role": "employee",
    "x-client-version": "web-fixture-0",
    "x-mode": "live",
    "x-ts-utc": nowIsoUtc(),
    "x-policy-version": "pv1",
  };
}

function buildMetaOnlyPayload({ requestId }) {
  return {
    request_id: requestId,
    mode: "live",
    signals: {
      status: "OK",
      count_open_items: 3,
      ts_utc: nowIsoUtc(),
      duration_ms_bucket: 250,
    }
  };
}

async function runOnce() {
  const requestId = rid();

  // P95 marks contract: input done → render done
  const inputDoneTs = perfNowMs();

  const resp = await fetch("/api/three_blocks", {
    method: "POST",
    headers: buildHeaders({ requestId }),
    body: JSON.stringify(buildMetaOnlyPayload({ requestId })),
  });

  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(`LIVE_DENY:${json.reason_code ?? "UNKNOWN"}`);
  }

  // runtime-ish headers (joinable with request_id)
  const runtimeLatencyMs = resp.headers.get("x-os-algo-latency-ms") ?? "";
  const runtimeManifestSha = resp.headers.get("x-os-algo-manifest-sha256") ?? "";

  // render
  const three = {
    request_id: requestId,
    marks: {
      input_done_ts_ms: inputDoneTs,
      three_blocks_render_done_ts_ms: perfNowMs(),
    },
    runtime: {
      latency_ms: runtimeLatencyMs,
      manifest_sha256: runtimeManifestSha,
    },
    blocks: json.blocks ?? {},
  };

  // minimal contract checks before showing OK marker
  if (!three.marks.input_done_ts_ms || !three.marks.three_blocks_render_done_ts_ms) {
    throw new Error("MARKS_MISSING");
  }
  if (three.marks.three_blocks_render_done_ts_ms < three.marks.input_done_ts_ms) {
    throw new Error("MARKS_ORDER_BAD");
  }
  if (typeof three.runtime.manifest_sha256 !== "string" || three.runtime.manifest_sha256.length < 10) {
    throw new Error("RUNTIME_HEADERS_MISSING");
  }

  out.textContent = JSON.stringify(three, null, 2);
  resultOk.dataset.requestId = requestId;
  resultOk.dataset.inputDoneTs = String(three.marks.input_done_ts_ms);
  resultOk.dataset.renderDoneTs = String(three.marks.three_blocks_render_done_ts_ms);
  resultOk.style.display = "block";
}

runBtn.addEventListener("click", async () => {
  resultOk.style.display = "none";
  out.textContent = "";
  try {
    await runOnce();
  } catch (e) {
    out.textContent = `ERROR:${String(e?.message ?? e)}`;
    throw e;
  }
});

