#!/usr/bin/env bash
set -euo pipefail

day="$(date -u +%Y-%m-%d)"
mkdir -p docs/ops/reports/archive

bash scripts/demo/run_scenario_doc_search_v0.sh
bash scripts/demo/run_scenario_write_approve_v0.sh
bash scripts/demo/run_scenario_helpdesk_ticket_v0.sh

# archive copies
cp -f docs/ops/reports/demo_doc_search_latest.json "docs/ops/reports/archive/${day}_demo_doc_search_latest.json"
cp -f docs/ops/reports/demo_doc_search_latest.md   "docs/ops/reports/archive/${day}_demo_doc_search_latest.md"

cp -f docs/ops/reports/demo_write_approve_latest.json "docs/ops/reports/archive/${day}_demo_write_approve_latest.json"
cp -f docs/ops/reports/demo_write_approve_latest.md   "docs/ops/reports/archive/${day}_demo_write_approve_latest.md"

cp -f docs/ops/reports/demo_helpdesk_ticket_latest.json "docs/ops/reports/archive/${day}_demo_helpdesk_ticket_latest.json"
cp -f docs/ops/reports/demo_helpdesk_ticket_latest.md   "docs/ops/reports/archive/${day}_demo_helpdesk_ticket_latest.md"

exit 0
