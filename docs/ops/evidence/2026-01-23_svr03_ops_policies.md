# SVR-03 Ops policies (masked)
Date: 2026-01-23

## Persistence
- atomic write: tmp -> fsync -> rename
- corruption: PERSIST_CORRUPTED fail-closed
- lock: retry + timeout (LOCK_TIMEOUT fail-closed)

## Audit
- daily file: audit_YYYY-MM-DD.json
- rotate: 1MB -> audit_YYYY-MM-DD.1.json
- retention: keep last 14 days only
- no raw payload stored

## Ops commands
- smoke:
  bash webcore_appcore_starter_4_17/scripts/ops/svr03_smoke.sh
- storage report:
  bash webcore_appcore_starter_4_17/scripts/ops/svr03_storage_report.sh

