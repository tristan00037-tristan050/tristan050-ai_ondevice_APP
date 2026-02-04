import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const ssotPath = path.join(process.cwd(), "docs/ops/contracts/PERF_P95_BUDGET_SSOT.json");
const ssot = JSON.parse(fs.readFileSync(ssotPath, "utf-8"));

const samples = Number(ssot.samples || 60);
const warmup = Number(ssot.warmup || 10);

// CPU-only mock pipeline that outputs the v3.3 3-block structure.
// This is a wiring harness to enforce the P95 gate. It does not perform network calls.
function mockButlerThreeBlocks(input) {
  // Deterministic CPU work to reduce noise and emulate compute without leaking text.
  // We hash meta-only signals, not raw input text.
  const meta = JSON.stringify({
    len: input.length,
    ts: 1700000000000,
    id: "req-0001"
  });

  let h = meta;
  for (let i = 0; i < 2000; i++) {
    h = crypto.createHash("sha256").update(h).digest("hex");
  }

  return {
    핵심_포인트: ["상태: OK", `해시:${h.slice(0, 12)}`],
    결정: "추가 확인 필요",
    다음_행동: ["요청 ID 확인", "권한/정책 헤더 확인"]
  };
}

function p95(msList) {
  const a = [...msList].sort((x, y) => x - y);
  const idx = Math.ceil(0.95 * a.length) - 1;
  return a[Math.max(0, Math.min(idx, a.length - 1))];
}

const input = "butler_mock_input";

const times = [];
for (let i = 0; i < warmup + samples; i++) {
  const t0 = process.hrtime.bigint();
  mockButlerThreeBlocks(input);
  const t1 = process.hrtime.bigint();
  const ms = Number(t1 - t0) / 1e6;
  if (i >= warmup) times.push(ms);
}

const p95ms = p95(times);
const out = {
  metric: ssot.metric,
  definition: ssot.definition,
  mode: ssot.mode,
  samples: times.length,
  p95_ms: Math.round(p95ms * 1000) / 1000,
  contract_ms: ssot.contract_ms,
  target_ms: ssot.target_ms
};

process.stdout.write(JSON.stringify(out) + "\n");

