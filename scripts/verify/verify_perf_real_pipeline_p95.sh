#!/usr/bin/env bash
set -euo pipefail

PERF_REAL_PIPELINE_WIRED_OK=0
PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK=0
PERF_REAL_PIPELINE_NO_RAW_OK=0
PERF_REAL_PIPELINE_P95_BUDGET_OK=0

cleanup() {
  echo "PERF_REAL_PIPELINE_WIRED_OK=${PERF_REAL_PIPELINE_WIRED_OK}"
  echo "PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK=${PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK}"
  echo "PERF_REAL_PIPELINE_NO_RAW_OK=${PERF_REAL_PIPELINE_NO_RAW_OK}"
  echo "PERF_REAL_PIPELINE_P95_BUDGET_OK=${PERF_REAL_PIPELINE_P95_BUDGET_OK}"

  if [[ "${PERF_REAL_PIPELINE_WIRED_OK}" == "1" ]] && \
     [[ "${PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK}" == "1" ]] && \
     [[ "${PERF_REAL_PIPELINE_NO_RAW_OK}" == "1" ]] && \
     [[ "${PERF_REAL_PIPELINE_P95_BUDGET_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

E2E="webcore_appcore_starter_4_17/scripts/web_e2e/run_p95_marks_e2e.mjs"
E2E_DIR="webcore_appcore_starter_4_17/scripts/web_e2e"
STORE="scripts/ops_hub/trace_realpath_store_v1.cjs"
BUDGET="docs/ops/contracts/PERF_REAL_PIPELINE_BUDGET_V1.txt"

[[ -s "$E2E" ]] || { echo "BLOCK: missing $E2E"; exit 1; }
[[ -s "$STORE" ]] || { echo "BLOCK: missing $STORE (M7-02 must be on main)"; exit 1; }
[[ -s "$BUDGET" ]] || { echo "BLOCK: missing $BUDGET"; exit 1; }

# Check dependencies exist (workflow must install)
test -d "${E2E_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }
test -d "${PLAYWRIGHT_BROWSERS_PATH:-${HOME}/.cache/ms-playwright}" || { echo "BLOCK: playwright browsers missing (workflow must install)"; exit 1; }

# 1) Run E2E and capture summary marker
OUT="$(node "$E2E" 2>&1)" || { echo "BLOCK: p95 marks e2e failed"; echo "$OUT"; exit 1; }

LINE="$(echo "$OUT" | grep -m1 -nE '^P95_MARKS_SUMMARY ' || true)"
[[ -n "$LINE" ]] || { echo "BLOCK: P95_MARKS_SUMMARY missing (measurement must not be silent)"; echo "$OUT"; exit 1; }

JSON="$(echo "$OUT" | sed -nE 's/^P95_MARKS_SUMMARY //p' | tail -n 1)"
[[ -n "$JSON" ]] || { echo "BLOCK: summary json missing"; exit 1; }

# 2) Parse + validate (no-raw)
RID="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.request_id||""))' "$JSON")"
LAT="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.runtime_latency_ms||""))' "$JSON")"
MSHA="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.runtime_manifest_sha256||""))' "$JSON")"

[[ "${#RID}" -ge 6 ]] || { echo "BLOCK: request_id missing/short"; exit 1; }
[[ "${#MSHA}" -ge 10 ]] || { echo "BLOCK: manifest sha missing/short"; exit 1; }

# latency must be numeric
node -e 'const s=String(process.argv[1]); const n=Number(s); if(!Number.isFinite(n) || n<0) process.exit(1);' "$LAT" \
  || { echo "BLOCK: latency not numeric"; exit 1; }

# no-raw scan (summary+stdout)
if echo "$OUT" | grep -nE '(raw_text|prompt|messages|document_body|BEGIN .* PRIVATE KEY|_TOKEN=|_PASSWORD=|DATABASE_URL=)' ; then
  echo "BLOCK: raw/secret-like content detected"
  exit 1
fi
PERF_REAL_PIPELINE_NO_RAW_OK=1
PERF_REAL_PIPELINE_WIRED_OK=1

# 3) Budget check from SSOT
BUDGET_MS="$(grep -nE '^P95_BUDGET_MS=' "$BUDGET" | tail -n 1 | cut -d= -f2 | tr -d '[:space:]')"
node -e 'const b=Number(process.argv[1]); const x=Number(process.argv[2]); if(!Number.isFinite(b)||!Number.isFinite(x)) process.exit(1); if(x>b) process.exit(1);' "$BUDGET_MS" "$LAT" \
  || { echo "BLOCK: budget exceeded (latency_ms > P95_BUDGET_MS)"; exit 1; }
PERF_REAL_PIPELINE_P95_BUDGET_OK=1

# 4) Join to Ops Hub realpath store (persist + idempotent + lookup by request_id)
RID="$RID" LAT="$LAT" MSHA="$MSHA" node - <<'NODE'
const os = require("os");
const path = require("path");
const { makeStore } = require("./scripts/ops_hub/trace_realpath_store_v1.cjs");

const rid = process.env.RID;
const lat = Number(process.env.LAT);
const msha = process.env.MSHA;

const db = path.join(os.tmpdir(), `ops_hub_perf_${Date.now()}_${Math.random().toString(16).slice(2)}.json`);
const store = makeStore(db);

const ev = {
  v: 1,
  event_id: `perf_${Date.now()}_${Math.random().toString(16).slice(2)}`,
  ts_utc: new Date().toISOString(),
  request_id: rid,
  event_type: "perf_real_pipeline_v1",
  trace: {
    runtime_algo_latency_ms: lat,
    runtime_manifest_sha256: msha,
  }
};

// 1st insert must be true
const r1 = store.ingest(ev);
if (!r1.inserted) process.exit(1);

// 2nd insert must be noop (idempotent)
const r2 = store.ingest(ev);
if (r2.inserted) process.exit(1);

// lookup must return >=1
const got = store.listByRequestId(rid);
if (!Array.isArray(got) || got.length < 1) process.exit(1);

process.exit(0);
NODE

PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK=1
exit 0

