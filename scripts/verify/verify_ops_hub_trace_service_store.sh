#!/usr/bin/env bash
set -euo pipefail

OPS_HUB_TRACE_SERVICE_PERSIST_OK=0
OPS_HUB_TRACE_IDEMPOTENT_OK=0
OPS_HUB_TRACE_NO_RAW_OK=0
OPS_HUB_TRACE_JOINABLE_OK=0

cleanup() {
  echo "OPS_HUB_TRACE_SERVICE_PERSIST_OK=${OPS_HUB_TRACE_SERVICE_PERSIST_OK}"
  echo "OPS_HUB_TRACE_IDEMPOTENT_OK=${OPS_HUB_TRACE_IDEMPOTENT_OK}"
  echo "OPS_HUB_TRACE_NO_RAW_OK=${OPS_HUB_TRACE_NO_RAW_OK}"
  echo "OPS_HUB_TRACE_JOINABLE_OK=${OPS_HUB_TRACE_JOINABLE_OK}"

  if [[ "$OPS_HUB_TRACE_SERVICE_PERSIST_OK" == "1" ]] && \
     [[ "$OPS_HUB_TRACE_IDEMPOTENT_OK" == "1" ]] && \
     [[ "$OPS_HUB_TRACE_NO_RAW_OK" == "1" ]] && \
     [[ "$OPS_HUB_TRACE_JOINABLE_OK" == "1" ]]; then
    exit 0
  fi
  exit 1
}
trap cleanup EXIT

command -v node >/dev/null 2>&1 || { echo "BLOCK: node missing"; exit 1; }

# 임시 DB 경로
DB="$(mktemp -t opshub_trace_sql_XXXXXX).db"
rm -f "$DB"

# ts-node가 필요하지만 verify 순수성 원칙에 따라 설치하지 않음 (workflow에서 설치)
command -v ts-node >/dev/null 2>&1 || { echo "BLOCK: ts-node missing (workflow must install)"; exit 1; }

ts-node - <<'NODE' "$DB"
const { openTraceStore } = require("./packages/ops-hub/src/store/trace_store_sql_v1");
const db = process.argv[1];
const store = openTraceStore(db);

const rid = "req_" + Date.now();
const ev = {
  v: 1,
  event_id: "ev_" + Date.now(),
  request_id: rid,
  trace: {
    ui_input_done_ms: 1,
    ui_render_done_ms: 2,
    runtime_algo_latency_ms: 3,
    runtime_manifest_sha256: "deadbeefdeadbeef",
    model_pack_id: "pack",
    model_pack_version: "1.0.0",
    reason_code: "OK"
  }
};

const r1 = store.ingest(ev);
if (!r1.inserted) process.exit(1);

// idempotent: same event_id again -> noop
const r2 = store.ingest(ev);
if (r2.inserted) process.exit(1);

const rows = store.listByRequestId(rid);
if (!rows || rows.length < 1) process.exit(1);

// no-raw: banned keys should not exist
const s = JSON.stringify(rows);
const banned = ["raw_text","prompt","messages","document_body","database_url","private_key"];
for (const b of banned) {
  if (s.toLowerCase().includes(b)) process.exit(2);
}

process.exit(0);
NODE

RC="$?"
if [[ "$RC" -eq 0 ]]; then
  OPS_HUB_TRACE_SERVICE_PERSIST_OK=1
  OPS_HUB_TRACE_IDEMPOTENT_OK=1
  OPS_HUB_TRACE_NO_RAW_OK=1
  OPS_HUB_TRACE_JOINABLE_OK=1
  exit 0
fi

echo "BLOCK: store verify failed rc=$RC"
exit 1

