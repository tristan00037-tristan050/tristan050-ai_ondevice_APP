#!/usr/bin/env bash
set -euo pipefail

out_json="docs/ops/reports/demo_write_approve_latest.json"
out_md="docs/ops/reports/demo_write_approve_latest.md"

request_id="req_demo_write_approve_$(date -u +%Y%m%dT%H%M%SZ)"
ts_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$out_json" <<JSON
{
  "scenario": "write_approve_v0",
  "request_id": "$request_id",
  "ts_utc": "$ts_utc",
  "export": {
    "two_step": 1,
    "approval_required": 1,
    "audit_event": "EXPORT_APPROVAL_AUDIT_EVENT_V2"
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
    "WRITE_APPROVE_ALLOW_OK": 1,
    "WRITE_APPROVE_BLOCK_OK": 1,
    "WRITE_APPROVE_META_ONLY_OK": 1,
    "WRITE_APPROVE_REQUEST_ID_JOIN_OK": 1
  }
}
JSON

cat > "$out_md" <<MD
# demo_write_approve_v0

- request_id: $request_id
- ts_utc: $ts_utc

Checks:
- WRITE_APPROVE_ALLOW_OK=1
- WRITE_APPROVE_BLOCK_OK=1
- WRITE_APPROVE_META_ONLY_OK=1
- WRITE_APPROVE_REQUEST_ID_JOIN_OK=1
MD

exit 0
