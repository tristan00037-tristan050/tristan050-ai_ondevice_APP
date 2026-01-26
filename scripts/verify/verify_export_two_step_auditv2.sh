#!/usr/bin/env bash
set -euo pipefail

SSOT="docs/ops/contracts/EXPORT_GATE_SSOT.json"
[ -f "$SSOT" ] || { echo "EXPORT_TWO_STEP_OK=0"; exit 1; }

# route existence (best-effort static)
rg -n "/api/v1/export/preview" webcore_appcore_starter_4_17/backend -S >/dev/null 2>&1 || { echo "EXPORT_TWO_STEP_OK=0"; exit 1; }
rg -n "/api/v1/export/approve" webcore_appcore_starter_4_17/backend -S >/dev/null 2>&1 || { echo "EXPORT_TWO_STEP_OK=0"; exit 1; }

# audit hook existence
rg -n "writeAuditEventV2\\(" webcore_appcore_starter_4_17/backend -S >/dev/null 2>&1 || { echo "EXPORT_APPROVAL_AUDITED_OK=0"; exit 1; }

echo "EXPORT_TWO_STEP_OK=1"
echo "EXPORT_APPROVAL_AUDITED_OK=1"

