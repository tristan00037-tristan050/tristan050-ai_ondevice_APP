#!/usr/bin/env bash
set -euo pipefail

PERF_REAL_PIPELINE_WIRED_OK=0
PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK=0
PERF_REAL_PIPELINE_NO_RAW_OK=0
PERF_REAL_PIPELINE_P95_BUDGET_OK=0
PERF_REAL_PIPELINE_MIN_SAMPLES_OK=0
PERF_REAL_PIPELINE_VARIANCE_OK=0

cleanup() {
  echo "PERF_REAL_PIPELINE_WIRED_OK=${PERF_REAL_PIPELINE_WIRED_OK}"
  echo "PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK=${PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK}"
  echo "PERF_REAL_PIPELINE_NO_RAW_OK=${PERF_REAL_PIPELINE_NO_RAW_OK}"
  echo "PERF_REAL_PIPELINE_P95_BUDGET_OK=${PERF_REAL_PIPELINE_P95_BUDGET_OK}"
  echo "PERF_REAL_PIPELINE_MIN_SAMPLES_OK=${PERF_REAL_PIPELINE_MIN_SAMPLES_OK}"
  echo "PERF_REAL_PIPELINE_VARIANCE_OK=${PERF_REAL_PIPELINE_VARIANCE_OK}"

  if [[ "${PERF_REAL_PIPELINE_WIRED_OK}" == "1" ]] && \
     [[ "${PERF_REAL_PIPELINE_REQUEST_ID_JOIN_OK}" == "1" ]] && \
     [[ "${PERF_REAL_PIPELINE_NO_RAW_OK}" == "1" ]] && \
     [[ "${PERF_REAL_PIPELINE_P95_BUDGET_OK}" == "1" ]] && \
     [[ "${PERF_REAL_PIPELINE_MIN_SAMPLES_OK}" == "1" ]] && \
     [[ "${PERF_REAL_PIPELINE_VARIANCE_OK}" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v node >/dev/null 2>&1 || { echo "BLOCK: node not found"; exit 1; }

E2E_DIR="webcore_appcore_starter_4_17/scripts/web_e2e"
N_RUNNER="scripts/perf/run_real_pipeline_p95_n.mjs"
STORE="scripts/ops_hub/trace_realpath_store_v1.cjs"
POLICY="docs/ops/contracts/PERF_REAL_PIPELINE_POLICY_V1.md"

[[ -s "$N_RUNNER" ]] || { echo "BLOCK: missing $N_RUNNER"; exit 1; }
[[ -s "$STORE" ]] || { echo "BLOCK: missing $STORE (M7-02 must be on main)"; exit 1; }
[[ -s "$POLICY" ]] || { echo "BLOCK: missing $POLICY"; exit 1; }

# Check dependencies exist (workflow must install)
test -d "${E2E_DIR}/node_modules" || { echo "BLOCK: node_modules missing (workflow must run npm ci)"; exit 1; }
test -d "${PLAYWRIGHT_BROWSERS_PATH:-${HOME}/.cache/ms-playwright}" || { echo "BLOCK: playwright browsers missing (workflow must install)"; exit 1; }

# 1) Run N samples and capture stats marker
MODE="${PERF_RUN_MODE:-merge}"
OUT="$(PERF_RUN_MODE="$MODE" node "$N_RUNNER" 2>&1)" || { echo "BLOCK: perf N-runner failed"; echo "$OUT"; exit 1; }

LINE="$(echo "$OUT" | grep -m1 -nE '^REAL_PIPELINE_STATS ' || true)"
[[ -n "$LINE" ]] || { echo "BLOCK: REAL_PIPELINE_STATS missing (measurement must not be silent)"; echo "$OUT"; exit 1; }

JSON="$(echo "$OUT" | sed -nE 's/^REAL_PIPELINE_STATS //p' | tail -n 1)"
[[ -n "$JSON" ]] || { echo "BLOCK: stats json missing"; exit 1; }

# 2) Parse stats
N_VAL="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.N||""))' "$JSON")"
STDDEV="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.stddev_ms||""))' "$JSON")"
P95="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.p95_ms||""))' "$JSON")"
BUDGET_MS="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.budget_ms||""))' "$JSON")"
MAX_STDDEV_MS="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.max_stddev_ms||""))' "$JSON")"
RID="$(node -e 'const j=JSON.parse(process.argv[1]); process.stdout.write(String(j.sample_request_id||""))' "$JSON")"

# 3) Validate N >= policy minimum
POLICY_N="$(grep -nE '^MERGE_N=' "$POLICY" | tail -n 1 | cut -d= -f2 | tr -d '[:space:]')"
if [[ "$MODE" == "schedule" ]]; then
  POLICY_N="$(grep -nE '^SCHEDULE_N=' "$POLICY" | tail -n 1 | cut -d= -f2 | tr -d '[:space:]')"
fi
node -e 'const n=Number(process.argv[1]); const p=Number(process.argv[2]); if(!Number.isFinite(n)||!Number.isFinite(p)) process.exit(1); if(n<p) process.exit(1);' "$N_VAL" "$POLICY_N" \
  || { echo "BLOCK: sample size N=${N_VAL} < policy minimum=${POLICY_N}"; exit 1; }
PERF_REAL_PIPELINE_MIN_SAMPLES_OK=1

# 4) Validate variance (stddev <= MAX_STDDEV_MS)
node -e 'const s=Number(process.argv[1]); const m=Number(process.argv[2]); if(!Number.isFinite(s)||!Number.isFinite(m)) process.exit(1); if(s>m) process.exit(1);' "$STDDEV" "$MAX_STDDEV_MS" \
  || { echo "BLOCK: stddev=${STDDEV}ms > max=${MAX_STDDEV_MS}ms"; exit 1; }
PERF_REAL_PIPELINE_VARIANCE_OK=1

# 5) Validate P95 budget
node -e 'const p=Number(process.argv[1]); const b=Number(process.argv[2]); if(!Number.isFinite(p)||!Number.isFinite(b)) process.exit(1); if(p>b) process.exit(1);' "$P95" "$BUDGET_MS" \
  || { echo "BLOCK: p95=${P95}ms > budget=${BUDGET_MS}ms"; exit 1; }
PERF_REAL_PIPELINE_P95_BUDGET_OK=1

# 6) no-raw scan (stats+stdout)
if echo "$OUT" | grep -nE '(raw_text|prompt|messages|document_body|BEGIN .* PRIVATE KEY|_TOKEN=|_PASSWORD=|DATABASE_URL=)' ; then
  echo "BLOCK: raw/secret-like content detected"
  exit 1
fi
PERF_REAL_PIPELINE_NO_RAW_OK=1
PERF_REAL_PIPELINE_WIRED_OK=1

# 4) Join to Ops Hub realpath store (persist + idempotent + lookup by request_id)
# Use sample request_id and p95 latency for join
RID="$RID" LAT="$P95" MSHA="dummy" node - <<'NODE'
const os = require("os");
const path = require("path");
const { makeStore } = require("./scripts/ops_hub/trace_realpath_store_v1.cjs");

const rid = process.env.RID;
const lat = Number(process.env.LAT);
const msha = process.env.MSHA || "dummy";

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

