const out = document.querySelector("#out");
const resultOk = document.querySelector("#result_ok");
const previewBtn = document.querySelector("#preview");
const approveBtn = document.querySelector("#approve");

function nowIsoUtc() { return new Date().toISOString(); }

function rid() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return [...a].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function sha256Hex(s) {
  // browser subtle crypto
  const enc = new TextEncoder().encode(s);
  return crypto.subtle.digest("SHA-256", enc).then((buf) => {
    const a = new Uint8Array(buf);
    return [...a].map((b) => b.toString(16).padStart(2, "0")).join("");
  });
}

const state = {
  request_id: rid(),
  export_token_hash: "",
  policy_version: "pv1",
};

function buildHeaders({ requestId, mode, policyVersion, idempotencyKey }) {
  const h = {
    "content-type": "application/json",
    "x-request-id": requestId,
    "x-device-id": "device_hash_demo",
    "x-role": "employee",
    "x-client-version": "web-fixture-0",
    "x-mode": mode,
    "x-ts-utc": nowIsoUtc(),
    "x-policy-version": policyVersion,
  };
  if (idempotencyKey) h["x-idempotency-key"] = idempotencyKey;
  return h;
}

function baseSignals() {
  return {
    status: "OK",
    count_open_items: 3,
    ts_utc: nowIsoUtc(),
    duration_ms_bucket: 250,
  };
}

async function doPreview() {
  const mode = "live";
  const payload = { request_id: state.request_id, mode, signals: baseSignals() };
  const headers = buildHeaders({ requestId: state.request_id, mode, policyVersion: state.policy_version });

  const resp = await fetch("/api/preview", { method: "POST", headers, body: JSON.stringify(payload) });
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(`PREVIEW_DENY:${json.reason_code ?? "UNKNOWN"}`);

  state.export_token_hash = json.export_token_hash;
  return { step: "preview", ok: true, export_token_hash: state.export_token_hash };
}

async function doApprove() {
  const mode = "live";
  const idem = await sha256Hex(`${state.request_id}:${state.export_token_hash}:${state.policy_version}`);

  const payload = {
    request_id: state.request_id,
    mode,
    export_token_hash: state.export_token_hash,
    policy_version: state.policy_version,
    signals: baseSignals(),
  };
  const headers = buildHeaders({
    requestId: state.request_id,
    mode,
    policyVersion: state.policy_version,
    idempotencyKey: idem,
  });

  const resp = await fetch("/api/approve", { method: "POST", headers, body: JSON.stringify(payload) });
  const json = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(`APPROVE_DENY:${json.reason_code ?? "UNKNOWN"}`);

  if (!json.audit_event_v2_id || typeof json.audit_event_v2_id !== "string") {
    throw new Error("APPROVE_MISSING_AUDIT_ID");
  }

  return { step: "approve", ok: true, audit_event_v2_id: json.audit_event_v2_id };
}

function render(step, obj) {
  out.textContent = JSON.stringify(obj, null, 2);
  resultOk.dataset.step = step;
  resultOk.style.display = "block";
}

previewBtn.addEventListener("click", async () => {
  resultOk.style.display = "none";
  out.textContent = "";
  try {
    const r = await doPreview();
    render("preview", r);
  } catch (e) {
    out.textContent = `ERROR:${String(e?.message ?? e)}`;
    throw e;
  }
});

approveBtn.addEventListener("click", async () => {
  resultOk.style.display = "none";
  out.textContent = "";
  try {
    if (!state.export_token_hash) throw new Error("MISSING_PREVIEW");
    const r = await doApprove();
    render("approve", r);
  } catch (e) {
    out.textContent = `ERROR:${String(e?.message ?? e)}`;
    throw e;
  }
});

