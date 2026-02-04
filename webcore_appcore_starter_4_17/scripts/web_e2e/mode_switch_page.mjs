const out = document.querySelector("#out");
const resultOk = document.querySelector("#result_ok");
const runBtn = document.querySelector("#run");

function nowIsoUtc() { return new Date().toISOString(); }

function rid() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return [...a].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function getMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}

function buildPolicyHeaders({ requestId, mode }) {
  return {
    "content-type": "application/json",
    "x-request-id": requestId,
    "x-device-id": "device_hash_demo",
    "x-role": "employee",
    "x-client-version": "web-fixture-0",
    "x-mode": mode,
    "x-ts-utc": nowIsoUtc(),
  };
}

function buildMetaOnlyPayload({ requestId, mode }) {
  return {
    request_id: requestId,
    mode,
    signals: {
      status: "OK",
      count_open_items: 3,
      ts_utc: nowIsoUtc(),
      duration_ms_bucket: 250,
    },
  };
}

function runMockEngine({ requestId }) {
  return {
    핵심_포인트: ["상태: OK", `요청:${requestId.slice(0, 8)}`],
    결정: "추가 확인 필요",
    다음_행동: ["정책 헤더 번들 점검", "Export 승인 감사 이벤트 확인"],
  };
}

async function runLive({ requestId }) {
  const mode = "live";
  const payload = buildMetaOnlyPayload({ requestId, mode });
  const headers = buildPolicyHeaders({ requestId, mode });

  const resp = await fetch("/api/echo", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(`LIVE_DENY:${json.reason_code ?? "UNKNOWN"}`);

  return {
    핵심_포인트: ["상태: OK", `echo:${json.echo?.request_id?.slice?.(0, 8) ?? "na"}`],
    결정: "Live 경로 확인 완료",
    다음_행동: ["audit_event_v2 기록 확인", "P95 이벤트 훅 연결"],
  };
}

function render(mode, threeBlock) {
  out.textContent = JSON.stringify(threeBlock, null, 2);
  resultOk.dataset.mode = mode;
  resultOk.style.display = "block";
}

runBtn.addEventListener("click", async () => {
  const mode = getMode();
  const requestId = rid();

  resultOk.style.display = "none";
  out.textContent = "";

  try {
    if (mode === "mock") return render("mock", runMockEngine({ requestId }));
    if (mode === "live") return render("live", await runLive({ requestId }));
    throw new Error("BAD_MODE");
  } catch (e) {
    out.textContent = `ERROR:${String(e?.message ?? e)}`;
    throw e;
  }
});
