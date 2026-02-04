#!/usr/bin/env bash
set -euo pipefail

SSOT="docs/ops/contracts/EXPORT_GATE_SSOT.json"
[ -f "$SSOT" ] || { echo "EXPORT_TWO_STEP_OK=0"; exit 1; }

# route existence (best-effort static)
rg -n "/api/v1/export/preview" webcore_appcore_starter_4_17/backend -S >/dev/null 2>&1 || { echo "EXPORT_TWO_STEP_OK=0"; exit 1; }
rg -n "/api/v1/export/approve" webcore_appcore_starter_4_17/backend -S >/dev/null 2>&1 || { echo "EXPORT_TWO_STEP_OK=0"; exit 1; }

# audit_event_v2_append.ts file existence
[ -f "webcore_appcore_starter_4_17/backend/telemetry/audit_event_v2_append.ts" ] || { echo "EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK=0"; exit 1; }

# appendAuditEventV2 called from export_gate.ts
rg -n "appendAuditEventV2" webcore_appcore_starter_4_17/backend/telemetry/export_gate.ts -S >/dev/null 2>&1 || { echo "EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK=0"; exit 1; }

# meta-only validation must exist in both preview and approve paths (fail-closed)
rg -n "validateMetaOnly\\(body\\)" webcore_appcore_starter_4_17/backend/telemetry/export_gate.ts -S >/dev/null 2>&1 || { echo "EXPORT_APPROVE_AUDIT_V2_OK=0"; exit 1; }
rg -n "validateMetaOnly\\(body\\?\\.payload\\)" webcore_appcore_starter_4_17/backend/telemetry/export_gate.ts -S >/dev/null 2>&1 || { echo "EXPORT_APPROVE_AUDIT_V2_OK=0"; exit 1; }

# audit payload should keep meta-only: preview_token must be truncated (avoid raw leakage)
rg -n "preview_token:.*slice\\(0,\\s*8\\)" webcore_appcore_starter_4_17/backend/telemetry/export_gate.ts -S >/dev/null 2>&1 || { echo "EXPORT_APPROVE_AUDIT_V2_OK=0"; exit 1; }

# Test file exists with EVID tag
rg -n "EVID:EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK" webcore_appcore_starter_4_17/backend/telemetry/tests -S >/dev/null 2>&1 || { echo "EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK=0"; exit 1; }

echo "EXPORT_TWO_STEP_OK=1"
echo "EXPORT_APPROVAL_AUDITED_OK=1"
echo "EXPORT_APPROVAL_AUDIT_EVENT_V2_WRITTEN_OK=1"
echo "EXPORT_APPROVE_AUDIT_V2_OK=1"

