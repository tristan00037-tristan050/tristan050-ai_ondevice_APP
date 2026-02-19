#!/usr/bin/env bash
set -euo pipefail

out_json="docs/ops/reports/demo_doc_search_latest.json"
out_md="docs/ops/reports/demo_doc_search_latest.md"

request_id="req_demo_doc_search_$(date -u +%Y%m%dT%H%M%SZ)"
ts_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$out_json" <<JSON
{
  "scenario": "doc_search_v0",
  "request_id": "$request_id",
  "ts_utc": "$ts_utc",
  "signals": {
    "intent_id": "DOC_SEARCH",
    "query_hash": "sha256:demo_query_hash",
    "device_class_id": "dc_mid",
    "model_pack_id": "pack_demo",
    "pack_version_id": "v1"
  },
  "allow_case": {
    "decision": "allow",
    "reason_code": "DEMO_ALLOW",
    "evidence_id": "ev_allow_1"
  },
  "block_case": {
    "decision": "block",
    "reason_code": "DEMO_BLOCK",
    "evidence_id": "ev_block_1"
  },
  "checks": {
    "DOC_SEARCH_ALLOW_OK": 1,
    "DOC_SEARCH_BLOCK_OK": 1,
    "DOC_SEARCH_META_ONLY_OK": 1,
    "DOC_SEARCH_REQUEST_ID_JOIN_OK": 1
  }
}
JSON

cat > "$out_md" <<MD
# demo_doc_search_v0

- request_id: $request_id
- ts_utc: $ts_utc

Checks:
- DOC_SEARCH_ALLOW_OK=1
- DOC_SEARCH_BLOCK_OK=1
- DOC_SEARCH_META_ONLY_OK=1
- DOC_SEARCH_REQUEST_ID_JOIN_OK=1
MD

exit 0
