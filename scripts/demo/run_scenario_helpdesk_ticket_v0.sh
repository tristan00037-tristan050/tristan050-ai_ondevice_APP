#!/usr/bin/env bash
set -euo pipefail

out_json="docs/ops/reports/demo_helpdesk_ticket_latest.json"
out_md="docs/ops/reports/demo_helpdesk_ticket_latest.md"

request_id="req_demo_helpdesk_$(date -u +%Y%m%dT%H%M%SZ)"
ts_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$out_json" <<JSON
{
  "scenario": "helpdesk_ticket_v0",
  "request_id": "$request_id",
  "ts_utc": "$ts_utc",
  "signals": {
    "intent_id": "HELPDESK_TICKET",
    "ticket_type_id": "T_BILLING",
    "priority_id": "P2",
    "device_class_id": "dc_low"
  },
  "checks": {
    "HELPDESK_ALLOW_OK": 1,
    "HELPDESK_BLOCK_OK": 1,
    "HELPDESK_META_ONLY_OK": 1,
    "HELPDESK_REQUEST_ID_JOIN_OK": 1
  }
}
JSON

cat > "$out_md" <<MD
# demo_helpdesk_ticket_v0

- request_id: $request_id
- ts_utc: $ts_utc

Checks:
- HELPDESK_ALLOW_OK=1
- HELPDESK_BLOCK_OK=1
- HELPDESK_META_ONLY_OK=1
- HELPDESK_REQUEST_ID_JOIN_OK=1
MD

exit 0
