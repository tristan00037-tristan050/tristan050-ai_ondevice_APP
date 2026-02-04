const out = document.querySelector("#out");
const resultOk = document.querySelector("#result_ok");
const runBtn = document.querySelector("#run");

function rid() {
  if (crypto?.randomUUID) return crypto.randomUUID();
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return [...a].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function postMeta(payload) {
  const resp = await fetch("/api/meta", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  });
  const json = await resp.json().catch(() => ({}));
  return { ok: resp.ok, json };
}

function baseGood() {
  return {
    request_id: `req_${rid().slice(0, 8)}`,
    mode: "live",
    signals: { status: "OK", count_open_items: 3, duration_ms_bucket: 250 }
  };
}

runBtn.addEventListener("click", async () => {
  resultOk.style.display = "none";
  out.textContent = "";

  const cases = [
    { name: "forbidden_top_raw_text", payload: { ...baseGood(), raw_text: "x" }, shouldPass: false },
    { name: "forbidden_signal_prompt", payload: { ...baseGood(), signals: { prompt: "x" } }, shouldPass: false },
    { name: "long_string", payload: { ...baseGood(), signals: { note: "a".repeat(200) } }, shouldPass: false },
    { name: "big_array", payload: { ...baseGood(), signals: { items: Array.from({ length: 200 }, (_, i) => i) } }, shouldPass: false },
    { name: "jwt_like", payload: { ...baseGood(), signals: { token: "aaa.bbb.ccc" } }, shouldPass: false },
    { name: "good_meta_only", payload: baseGood(), shouldPass: true },
  ];

  const results = [];
  for (const c of cases) {
    const r = await postMeta(c.payload);
    results.push({ name: c.name, ok: r.ok, reason_code: r.json?.reason_code ?? "" });
    if (c.shouldPass && !r.ok) throw new Error(`CASE_FAIL_SHOULD_PASS:${c.name}`);
    if (!c.shouldPass && r.ok) throw new Error(`CASE_PASS_SHOULD_FAIL:${c.name}`);
  }

  out.textContent = JSON.stringify({ results }, null, 2);
  resultOk.style.display = "block";
});

